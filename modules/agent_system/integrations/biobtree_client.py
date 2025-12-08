"""BioBTree gRPC client for agent system."""

import asyncio
from typing import Dict, List, Optional
import grpc
from google.protobuf.json_format import MessageToDict

from .biobtree_pb import app_pb2, app_pb2_grpc
from ..core.config import BioBTreeConfig


class BioBTreeClient:
    """
    Async gRPC client for BioBTree database.

    Provides high-performance access to BioBTree's deterministic mappings
    across 40+ biological databases using gRPC binary protocol.

    Responses are automatically converted from Protocol Buffers to Python
    dictionaries for seamless integration with LLM APIs.
    """

    def __init__(self, config: BioBTreeConfig):
        """
        Initialize BioBTree gRPC client.

        Args:
            config: BioBTree configuration (gRPC host, port, etc.)
        """
        self.config = config
        self.channel: Optional[grpc.aio.Channel] = None
        self.stub: Optional[app_pb2_grpc.BiobtreeServiceStub] = None
        self._connected = False

    async def connect(self):
        """Establish gRPC connection to BioBTree server."""
        if self._connected:
            return

        target = f"{self.config.grpc.host}:{self.config.grpc.port}"

        # Create channel with keepalive settings
        options = [
            ('grpc.keepalive_time_ms', self.config.grpc.keepalive_time * 1000),
            ('grpc.keepalive_timeout_ms', 10000),
            ('grpc.keepalive_permit_without_calls', True),
            ('grpc.http2.max_pings_without_data', 0),
        ]

        self.channel = grpc.aio.insecure_channel(target, options=options)
        self.stub = app_pb2_grpc.BiobtreeServiceStub(self.channel)
        self._connected = True

    async def close(self):
        """Close gRPC connection."""
        if self.channel:
            await self.channel.close()
            self._connected = False

    async def __aenter__(self):
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()

    async def _execute_with_retry(self, func, *args, **kwargs):
        """Execute gRPC call with retry logic."""
        for attempt in range(self.config.retry_attempts):
            try:
                return await func(*args, **kwargs)
            except grpc.RpcError as e:
                if attempt == self.config.retry_attempts - 1:
                    raise
                # Exponential backoff
                await asyncio.sleep(self.config.retry_delay * (2 ** attempt))
                # Reconnect if disconnected
                if e.code() == grpc.StatusCode.UNAVAILABLE:
                    await self.close()
                    await self.connect()

    async def search(
        self,
        terms: List[str],
        dataset: Optional[str] = None,
        detail: bool = False
    ) -> Dict:
        """
        Search for identifiers across datasets.

        Args:
            terms: Search terms or identifiers
            dataset: Optional dataset to search in
            detail: If True, include full cross-references

        Returns:
            Search results as Python dict

        Example:
            >>> results = await client.search(["BRCA1"], dataset="hgnc", detail=True)
        """
        await self.connect()

        request = app_pb2.SearchRequest(
            terms=terms,
            dataset=dataset or "",
            detail=detail
        )

        response = await self._execute_with_retry(
            self.stub.Search,
            request,
            timeout=self.config.grpc.timeout
        )

        # Convert protobuf to dict for LLM consumption
        return MessageToDict(
            response,
            preserving_proto_field_name=True
        )

    async def map_query(
        self,
        terms: List[str],
        mapfilter: str,
        mode: str = "lite",
        page: str = ""
    ) -> Dict:
        """
        Execute BioBTree mapping query with chain syntax.

        Args:
            terms: Input identifiers
            mapfilter: Mapping chain query (e.g., ">>uniprot>>chembl_target")
            mode: Response mode - "lite" (default, compact IDs) or "full" (all attributes)
            page: Pagination token for subsequent pages

        Returns:
            Mapping results as Python dict

            Lite mode response:
            {
                "results_lite": {
                    "mode": "lite",
                    "query": {"terms": [...], "chain": "...", "raw": "..."},
                    "mappings": [
                        {"input": "TP53", "source": {"d": "ensembl", "id": "...", "has_attr": true},
                         "targets": [{"d": "uniprot", "id": "P04637", "has_attr": true}]}
                    ],
                    "stats": {"total_terms": 2, "mapped": 2, "failed": 0, "total_targets": 2},
                    "pagination": {"page": 1, "has_next": false}
                }
            }

            Full mode response:
            {
                "results": {
                    "results": [...],  // Full Xref objects with all attributes
                    "query": {...},
                    "stats": {...},
                    "pagination": {...}
                }
            }

        Example:
            >>> # Lite mode (default) - compact IDs only
            >>> result = await client.map_query(["EGFR"], ">>ensembl>>uniprot")

            >>> # Full mode - all attributes
            >>> result = await client.map_query(["EGFR"], ">>ensembl>>uniprot", mode="full")
        """
        await self.connect()

        request = app_pb2.MappingRequest(
            terms=terms,
            query=mapfilter,
            mode=mode,
            page=page
        )

        response = await self._execute_with_retry(
            self.stub.Mapping,
            request,
            timeout=self.config.grpc.timeout
        )

        return MessageToDict(
            response,
            preserving_proto_field_name=True,
        )

    async def get_entry(
        self,
        identifier: str,
        dataset: str
    ) -> Dict:
        """
        Get specific entry from dataset.

        Args:
            identifier: Entry ID
            dataset: Dataset name (e.g., "uniprot", "chembl")

        Returns:
            Entry data as Python dict

        Example:
            >>> entry = await client.get_entry("P04637", "uniprot")
        """
        await self.connect()

        request = app_pb2.EntryRequest(
            identifier=identifier,
            dataset=dataset
        )

        response = await self._execute_with_retry(
            self.stub.Entry,
            request,
            timeout=self.config.grpc.timeout
        )

        return MessageToDict(
            response,
            preserving_proto_field_name=True,
        )

    async def filter_query(
        self,
        identifier: str,
        dataset: str,
        filters: List[str],
        page: int = 1
    ) -> Dict:
        """
        Execute filtered query.

        Args:
            identifier: Entry identifier
            dataset: Dataset name
            filters: List of dataset names to filter by
            page: Page number for pagination

        Returns:
            Filtered results as Python dict

        Example:
            >>> result = await client.filter_query(
            ...     "P04637",
            ...     "uniprot",
            ...     ["go", "reactome"]
            ... )
        """
        await self.connect()

        request = app_pb2.FilterRequest(
            identifier=identifier,
            dataset=dataset,
            filters=filters,
            page=page
        )

        response = await self._execute_with_retry(
            self.stub.Filter,
            request,
            timeout=self.config.grpc.timeout
        )

        return MessageToDict(
            response,
            preserving_proto_field_name=True,
        )

    async def get_metadata(self) -> Dict:
        """
        Get metadata about available datasets.

        Returns:
            Dataset metadata as Python dict

        Example:
            >>> meta = await client.get_metadata()
            >>> print(meta.keys())  # Available datasets
        """
        await self.connect()

        request = app_pb2.MetaRequest()

        response = await self._execute_with_retry(
            self.stub.Meta,
            request,
            timeout=self.config.grpc.timeout
        )

        return MessageToDict(
            response,
            preserving_proto_field_name=True,
        )


# Factory function for easier instantiation
def create_biobtree_client(config: BioBTreeConfig) -> BioBTreeClient:
    """
    Create and return a BioBTree client instance.

    Args:
        config: BioBTree configuration

    Returns:
        Configured BioBTree client
    """
    return BioBTreeClient(config)
