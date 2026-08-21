# Implementation Plan - AWS Lambda Integration (qplambda.py)

This plan outlines the design and implementation of a serverless AWS Lambda function handler (`qplambda.py`) that incorporates all current backend functionalities of `app.py`. It addresses the stateless nature of AWS Lambda by storing the generated FAISS vector indices in S3 and downloading them dynamically during question generation.

## User Review Required

> [!IMPORTANT]
> - **Stateless Vector Store Management**: Unlike the server-based `app.py` which saves FAISS indices to a local folder and reads them locally on subsequent requests, AWS Lambda is stateless. The proposed solution is to save FAISS indices to S3 in `/api/analyse-note` and pull them from S3 in `/api/generate-questions`.
> - **CORS Setup**: AWS Lambda will return appropriate CORS headers (`Access-Control-Allow-Origin: *`, etc.) to support end-to-end connection workflow when the frontend is served via CloudFront.
> - **MongoDB Fallback**: If MongoDB is not configured or fails to connect, the system will use base64-encoded S3 keys as fallback stateless note IDs, ensuring the backend functions correctly even without MongoDB.

## Proposed Changes

### Backend Component

#### [NEW] [qplambda.py](file:///d:/Github_Codes/Question_paper/Question_maker_feedback_loop/qplambda.py)
A new script containing the AWS Lambda entrypoint (`lambda_handler`) and individual handler functions mimicking the endpoints in `app.py`.

- **CORS Handling**: Automatically responds to `OPTIONS` preflight requests and appends CORS headers to all responses.
- **Multipart Form Parsing**: Implements a standard-library-based `multipart/form-data` parser using the Python `email` package to handle PDF file uploads dynamically.
- **FAISS S3 Sync**:
  - `analyse-note`: Processes PDFs, builds FAISS vector indices, and uploads `index.faiss` and `index.pkl` to S3 under `vectorstores/{note_id}/`.
  - `generate-questions`: Checks if any requested topics contain a `noteId`, downloads the index files from S3 to `/tmp/vectorstores/{note_id}/`, and loads the FAISS vectorstore.
- **Test Routes**: Supports `/api/mylangtest` (POST) and `/api/mylangtest-get` (GET) routes to allow easy testing with mock JSON configurations.

## Verification Plan

### Manual Verification
1. **Local Test Script**: Create a test script in the artifacts/scratch folder to simulate AWS API Gateway request payloads and invoke the `lambda_handler` function locally.
2. **Endpoint Validation**:
   - Test `mylangtest` with a simple JSON payload to confirm the Azure OpenAI pipeline works.
   - Test PDF upload, analysis, and question generation under simulated Lambda conditions.
