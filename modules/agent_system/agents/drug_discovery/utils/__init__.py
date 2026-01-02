"""Utility Functions for Drug Discovery Agent.

Shared utilities used across paths and extractors:
- drug_names: Drug name selection (INN preferred over codes)

Note: Pagination is now handled by BioBTreeClient.map_query_all_pages()
      in integrations/biobtree_client.py (shared across all agents).
"""

from .drug_names import get_best_drug_name

__all__ = ["get_best_drug_name"]
