# BioYoda Code Quality Improvements TODO

## IMMEDIATE PRIORITY (Week 1-2)

### Error Handling & Resilience
- [ ] **Replace silent exception handling in process_single_file.py**
  ```python
  # Replace line 92-93:
  except Exception:
      pass
  # With specific error handling:
  except ET.ParseError as e:
      log_with_timestamp(f"XML parsing error for PMID {pmid}: {e}")
      continue
  except Exception as e:
      log_with_timestamp(f"Unexpected error processing PMID {pmid}: {e}")
      continue
  ```

- [ ] **Add proper error handling in API startup (api.py)**
  ```python
  @app.on_event("startup")
  def load_resources():
      try:
          app.state.model = SentenceTransformer(MODEL_NAME)
          if not os.path.exists(FAISS_INDEX_PATH):
              raise FileNotFoundError(f"Index file not found: {FAISS_INDEX_PATH}")
          app.state.index = faiss.read_index(FAISS_INDEX_PATH)
          with open(METADATA_PATH, 'r') as f:
              app.state.metadata = json.load(f)
          log_with_timestamp("Resources loaded successfully.")
      except Exception as e:
          log_with_timestamp(f"Failed to load resources: {e}")
          raise
  ```

### Input Validation
- [ ] **Add input validation to API endpoints**
  - Validate query string length and content
  - Validate top_k parameter bounds (1-100)
  - Add request size limits

- [ ] **Add file path validation**
  - Check file existence before processing
  - Validate file extensions and formats
  - Add path traversal protection

## SHORT-TERM (Month 1)

### Logging & Monitoring
- [ ] **Implement structured logging**
  - Replace print statements with proper logging module
  - Add log levels (DEBUG, INFO, WARNING, ERROR)
  - Create log rotation for production

- [ ] **Add comprehensive logging to data_download.py**
  - Log FTP connection status
  - Log download speeds and file sizes
  - Log retry attempts and failures

- [ ] **Add processing metrics logging**
  - Track processing speed (abstracts per minute)
  - Log memory usage during processing
  - Track FAISS index build times

### Testing Infrastructure
- [ ] **Create unit tests structure**
  ```
  tests/
  ├── test_process_single_file.py
  ├── test_api.py
  ├── test_data_download.py
  ├── test_merge.py
  └── fixtures/
      └── sample_pubmed.xml.gz
  ```

- [ ] **Implement core unit tests**
  - Test XML parsing with malformed data
  - Test FAISS index creation and search
  - Test API endpoints with various inputs
  - Test merge functionality with sample data

### Data Integrity
- [ ] **Add file integrity checks**
  - MD5/SHA256 checksums for downloaded files
  - Validate XML structure before processing
  - Check FAISS index consistency

- [ ] **Add data validation**
  - Validate PMID format and uniqueness
  - Check abstract text quality (length, encoding)
  - Verify vector dimensions match model

## MEDIUM-TERM (Month 2-3)

### Network Resilience
- [ ] **Implement retry mechanisms for FTP downloads**
  ```python
  from tenacity import retry, stop_after_attempt, wait_exponential

  @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
  def download_ftp_file_with_retry(ftp, remote_path, local_path):
      # existing download logic
  ```

- [ ] **Add connection timeout handling**
  - FTP connection timeouts
  - Large file download timeouts
  - API response timeouts

### API Enhancements
- [ ] **Add API authentication**
  - Implement API key authentication
  - Add rate limiting per user
  - Create user management system

- [ ] **Enhance API endpoints**
  - Add health check endpoint (`/health`)
  - Add metrics endpoint (`/metrics`)
  - Add index statistics endpoint (`/stats`)

- [ ] **Implement full RAG endpoint**
  - Add OpenAI API integration
  - Implement prompt engineering
  - Add response caching

### Performance Optimization
- [ ] **Optimize memory usage**
  - Implement batch processing for large XML files
  - Add memory monitoring and cleanup
  - Optimize FAISS index parameters

- [ ] **Add caching layers**
  - Cache frequently accessed metadata
  - Implement query result caching
  - Add model embedding caching

### Production Readiness
- [ ] **Add container support**
  - Create Dockerfile for API service
  - Create Docker Compose for full stack
  - Add Kubernetes manifests

- [ ] **Implement monitoring**
  - Add Prometheus metrics
  - Create Grafana dashboards
  - Set up alerting for failures

## LONG-TERM (Month 3+)

### Scalability
- [ ] **Implement distributed processing**
  - Add support for multiple worker nodes
  - Implement distributed FAISS indices
  - Add load balancing for API

- [ ] **Database integration**
  - Replace JSON metadata with proper database
  - Add full-text search capabilities
  - Implement backup and recovery

### Security
- [ ] **Security hardening**
  - Add input sanitization
  - Implement proper authentication/authorization
  - Add security headers to API responses
  - Conduct security audit

### Documentation
- [ ] **Create comprehensive documentation**
  - API documentation with OpenAPI/Swagger
  - Installation and deployment guides
  - Architecture documentation
  - Troubleshooting guides

### Advanced Features
- [ ] **Multi-source data integration**
  - Add PMC full-text processing
  - Implement ClinicalTrials.gov integration
  - Add patent data processing

- [ ] **Advanced search features**
  - Implement query expansion
  - Add result re-ranking
  - Implement faceted search

---

## Notes for Implementation

1. **Priority Order**: Work through items in the order listed - immediate items address critical stability issues
2. **Testing**: Add tests for each new feature as you implement it
3. **Documentation**: Update CLAUDE.md and README.md as you make changes
4. **Backwards Compatibility**: Ensure changes don't break existing functionality
5. **Performance**: Benchmark performance impact of each change

## Quick Wins (Can be done in parallel)
- Replace hardcoded paths with config variables
- Add basic input validation to API
- Implement proper logging in place of print statements
- Add file existence checks before processing
- Create basic unit test structure