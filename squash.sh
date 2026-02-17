#!/bin/bash
set -e

# Create orphan branch with first commit's content
git checkout --orphan squashed-main 8754163

# 1. Initial prototype + frontend redesign
git checkout 986442c -- .
git add -A
git commit -m "Implement LabelVerify AI prototype with React frontend and FastAPI backend

- Multi-panel label image extraction using LLM vision
- Side-by-side comparison of extracted vs declared values  
- Compliance checking against TTB regulations
- Single-page React frontend with polished visual identity
- FastAPI backend with SQLite persistence"

# 2. Deployment and CI/CD  
git checkout 33c0985 -- .
git add -A
git commit -m "Add deployment configuration and CI/CD pipeline

- Deploy backend to Railway with health checks
- Add fail-fast config validation and CI pipeline
- Fix code quality and security issues
- Add provider-agnostic LLM extraction (Anthropic/Groq)"

# 3. Test infrastructure
git checkout f7aec35 -- .
git add -A
git commit -m "Add comprehensive test infrastructure and benchmarking

- Expand test fixtures from 8 to 46 labels
- Add benchmark tooling with caching and throttling
- Package test data with PDF parser utilities"

# 4. Human review + batch processing  
git checkout c94af8f -- .
git add -A
git commit -m "Add human review flow and batch processing

- Human review UI with side-by-side text verification
- Batch upload with parallel PDF processing
- TTB class/type normalization for smarter matching
- OCR hyphen normalization (95% benchmark accuracy)"

# 5. Extraction accuracy
git checkout 99d5d87 -- .
git add -A
git commit -m "Improve extraction accuracy with re-extraction strategies

- Warning-focused re-extraction (97.5% benchmark)
- Image preprocessing for small labels  
- Class/type subset word matching
- 66 independent business logic tests
- Integrate ComplianceChecker into pipeline"

# 6. COLA PDF workflow
git checkout fc63636 -- .
git add -A
git commit -m "Refactor to COLA PDF workflow with LLM cost tracking

- Single COLA PDF input workflow
- LLM token/time tracking across pipeline
- Specialty class/type verification via re-extraction
- Brand confirmation re-extraction on mismatch
- Temperature=0 for deterministic results"

# 7. Evaluation framework  
git checkout aa11fbe -- .
git add -A
git commit -m "Add evaluation framework and cost tracking

- End-to-end pipeline evaluation
- Cost module for LLM spend tracking
- Switch to Sonnet for improved accuracy"

# 8. Pipeline optimization
git checkout 9b40073 -- .
git add -A
git commit -m "Optimize extraction pipeline for performance

- Switch to Haiku for initial extraction with prompt caching
- Split extraction into 3 focused parallel calls
- Replace structured extraction with transcribe-then-search
- Add retry with backoff for rate limits
- Achieve 5-second target response time"

# 9. Matching accuracy
git checkout dc6af31 -- .
git add -A
git commit -m "Fix matching accuracy for edge cases

- ABV re-extraction on mismatch with near-miss tolerance
- Net contents re-extraction on mismatch/missing
- Class variant matching (cerveza=beer, etc.)
- Prefix matching for compound words
- Upgrade re-extractions to Sonnet for accuracy"

# 10. Final - MUST match main-backup exactly
git rm -rf . 2>/dev/null || true
git checkout main-backup -- .
git add -A
git commit -m "Refactor architecture and add comprehensive frontend tests

- 4-phase architecture cleanup removing 2,153 lines of dead code
- Add 142 frontend tests across 17 test files  
- Use Haiku for transcription, Sonnet for re-extractions
- Improve text matcher to reduce re-extraction calls"

echo "Done! Verifying..."
diff_count=$(git diff main-backup --stat | wc -l)
if [ "$diff_count" -eq "0" ]; then
  echo "✓ Trees match exactly"
else
  echo "✗ $diff_count differences found"
fi
