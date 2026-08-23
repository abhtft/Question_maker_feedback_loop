# Asynchronous AWS Step Functions Backend Implementation

This plan outlines the design and implementation of modular Lambda functions for the AWS Step Functions workflow.

Instead of a single monolith Lambda function (`qplambda.py`), we will create a dedicated `backend/step_lambda` folder containing individual handler files. All functions will be packaged into a single Docker container image and deployed using different Lambda entrypoint handlers.

---

## User Review Required

> [!IMPORTANT]
> **Single Container Deployment Strategy:**
> To simplify deployment and minimize AWS ECR storage costs, all Lambda handler files will reside in the same codebase and use a single Dockerfile (`Dockerfile.step`). When creating the 6 different Lambda functions in AWS Console/CloudFormation, you will configure each with a different **CMD** command pointing to the corresponding handler.
> E.g., `backend/step_lambda/start_task.handler`.

> [!WARNING]
> **API Gateway Timeout Resolution:**
> This changes the frontend API interaction to be asynchronous. The client will receive an immediate `202 Accepted` response with a `task_id` and must poll the `/api/status/{task_id}` endpoint to track progress.

---

## Proposed Changes

We will create a new directory [`backend/step_lambda`](file:///d:/Github_Codes/Question_paper/Question_maker_feedback_loop/backend/step_lambda) containing the following handlers:

### 1. [NEW] [`start_task.py`](file:///d:/Github_Codes/Question_paper/Question_maker_feedback_loop/backend/step_lambda/start_task.py)
* **Purpose:** Handles the API request POST `/api/generate-questions`. Initiates the Step Functions State Machine execution and creates a DynamoDB record with `status='PENDING'`.

### 2. [NEW] [`process_pdf.py`](file:///d:/Github_Codes/Question_paper/Question_maker_feedback_loop/backend/step_lambda/process_pdf.py)
* **Purpose:** If `noteId` is provided, downloads the PDF from S3, parses it, builds a FAISS index, and uploads index files to S3. Updates database status to `PROCESSING_PDF`.

### 3. [NEW] [`generate_questions.py`](file:///d:/Github_Codes/Question_paper/Question_maker_feedback_loop/backend/step_lambda/generate_questions.py)
* **Purpose:** Reads context from S3 (if applicable), generates questions in batches, and runs verification. Increments retry attempts if validation fails. Updates database status to `GENERATING_QUESTIONS` or `VERIFICATION_FAILED`.

### 4. [NEW] [`compile_pdf.py`](file:///d:/Github_Codes/Question_paper/Question_maker_feedback_loop/backend/step_lambda/compile_pdf.py)
* **Purpose:** Generates a PDF via `CreatePDF` and uploads it to S3, generating a pre-signed URL. Updates database status to `COMPILING_PDF`.

### 5. [NEW] [`trigger_webhooks.py`](file:///d:/Github_Codes/Question_paper/Question_maker_feedback_loop/backend/step_lambda/trigger_webhooks.py)
* **Purpose:** Invokes Google Form and n8n webhooks. Updates database status to `SENDING_NOTIFICATIONS`.

### 6. [NEW] [`update_db_completed.py`](file:///d:/Github_Codes/Question_paper/Question_maker_feedback_loop/backend/step_lambda/update_db_completed.py)
* **Purpose:** Finalizes the database entry with generated questions, PDF url, and updates status to `COMPLETED`.

### 7. [NEW] [`status_checker.py`](file:///d:/Github_Codes/Question_paper/Question_maker_feedback_loop/backend/step_lambda/status_checker.py)
* **Purpose:** Serves the status polling route `GET /api/status/{task_id}` to retrieve state from DynamoDB.

### 8. [NEW] [`Dockerfile.step`](file:///d:/Github_Codes/Question_paper/Question_maker_feedback_loop/Dockerfile.step)
* **Purpose:** Dockerfile optimized for Step Functions single-container deployment.

---

## Verification Plan

### Automated Tests
* We can run dry-run script executions locally by mocking Step Functions events.
* We will verify syntax correctness and imports using:
  ```bash
  python -m py_compile backend/step_lambda/*.py
  ```

### Manual Verification
* Deploy the Docker image to AWS ECR.
* Setup Lambda functions with matching handlers.
* Build the state machine in AWS Step Functions.
* Trigger a test run and monitor execution logs in the Step Functions console.
