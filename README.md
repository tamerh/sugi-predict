 Issues & Tasks:

    1.1: Project Setup & Orchestration

      [ ]  Task: Initialize GitHub repository with a clear project structure.

      [ ]  Task: Set up n8n in a Docker container for workflow orchestration.

        Task: Configure cloud object storage (e.g., an S3-compatible service) to act as the central store for all raw and processed data.

    1.2: Data Acquisition Pipeline

        Task: Implement a script for the initial bulk download of the PubMed baseline via FTP.

        Task: Implement a script to download the PMC Open Access (OA) full-text subset.

        Task: Build a robust client for the Europe PMC API to download all preprint records.

    1.3: Data Processing & Cleaning

        Task: Develop a unified XML parser to handle both PubMed and PMC data formats.

        Task: Implement a de-duplication service that uses a persistent store (e.g., a simple database or file) to track processed PMIDs and DOIs.

        Task: Implement a semantic chunking module to split text into meaningful pieces.

    1.4: AI Processing (Embedding & Indexing)

        Task: Research and benchmark open-source embedding models. Select one based on performance vs. size trade-offs.

        Task: Implement the batch embedding pipeline to convert all text chunks into vectors.

        Task: Implement the script to build, compress, and save portable FAISS indices from the generated vectors.

    1.5: Data Packaging & Finalization

        Task: Design the schema for the metadata database.

        Task: Implement a script to package all metadata (authors, dates, sources, etc.) into a single, portable database file (e.g., SQLite).

        Task: Create a Dockerfile for the entire Stage 0 pipeline to ensure it's reproducible.

        Task: Write a final script to upload all assets (embeddings, FAISS indices, metadata DB) to cloud object storage.

🚀 Epic 2: Stage 1 - MVP Launch & Validation

(Timeline: Starts concurrently with Epic 1, extends beyond the 3 months)
The goal of this epic is to launch a live, usable product that solves a single niche problem.

Issues & Tasks:

    2.1: API Backend (FastAPI)

        Task: Set up the initial FastAPI application structure.

        Task: Implement the abstract VectorDBRepository (the Data Access Layer / Adapter Pattern).

        Task: Implement the PineconeRepository as the first concrete adapter.

        Task: Build a utility to load the Stage 0 assets into Pinecone Serverless.

    2.2: Core RAG Logic

        Task: Implement the real-time query embedding logic using the OpenAI API.

        Task: Implement the prompt engineering logic for the final answer synthesis.

        Task: Implement the main /query endpoint that integrates the full RAG pipeline (embed -> retrieve -> generate).

    2.3: First Niche Product (UI)

        Task: Choose a niche to target first (e.g., "ClinTrial Copilot").

        Task: Build a minimal, functional user interface (e.g., using Streamlit for speed or a simple React app).

        Task: Connect the UI to the FastAPI backend.

    2.4: Deployment & Go-to-Market

        Task: Deploy the FastAPI application to a managed service like Railway.

        Task: Implement simple API key authentication.

        Task: Onboard 5-10 beta testers for initial feedback.

🧩 Epic 3: Data Expansion Module

(Timeline: After the MVP is stable)
This epic directly addresses your goal of adding new data sources.

Issues & Tasks:

    Task: Research and evaluate patent data sources (Google Patents, USPTO).

    Task: Research and evaluate drug/compound databases (PubChem, DrugBank).

    Task: Refactor the Stage 0 pipeline to be a modular system where new data sources can be added as plugins.

    Task: Implement the full ingestion pipeline for patent data as the first new module.

    Task: Explore creating specialized, combined indexes (e.g., a "Drug & Patent" index).

💰 Epic 4: Stage 2 - Scale & Optimization

(Timeline: Triggered by revenue/cost milestones)
The goal of this epic is to migrate to a more cost-effective, self-hosted infrastructure.

Issues & Tasks:

    Task: Set up billing alerts and a dashboard to monitor Pinecone costs against revenue.

    Task: Implement the QdrantRepository as the second concrete adapter for your DAL.

    Task: Plan the migration: provision servers (e.g., on Hetzner), set up a Qdrant instance, and load the Stage 0 assets.

    Task: Execute the migration by switching the adapter in your live application.
