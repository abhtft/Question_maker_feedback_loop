# ⚖️ Architectural Judgement: AWS ECS vs. AWS Lambda
### Prashnotri Question Paper Generator (2-5 Users)

This document provides a comparative analysis of deploying the Prashnotri backend container (~480MB) using **AWS Lambda (Serverless)** vs. **AWS ECS (Fargate)**, with a final recommendation for a user base of 2-5 concurrent users.

---

## 📊 Summary Comparison

| Metric | AWS Lambda (Serverless) | AWS ECS (Fargate) |
| :--- | :--- | :--- |
| **Idle Cost** | 💰 **$0.00** (Pay only when executing) | 💸 **~$35 - $45 / month** (Task + Load Balancer 24/7) |
| **Active Cost** | Negligible (Covered by 1M free requests/mo) | Included in the flat 24/7 billing |
| **Cold Starts** | ⚠️ **3 - 5 seconds** (first request after idle) | None (Container is always warm and running) |
| **Setup Complexity** | 🟢 **Low** (Simple Lambda + API Gateway) | 🔴 **High** (Cluster, VPC, Subnets, ALB, Target Groups) |
| **Scale to Zero** | 🟢 **Automatic** (Built-in) | 🔴 **No** (Needs manual scaling or complex scripts) |
| **Timeout Limits** | 15 minutes (More than enough) | Unlimited |
| **Maintenance** | None (AWS manages the host platform) | Occasional security patching / cluster updates |

---

## 🔍 In-Depth Analysis

### 1. Cost Efficiency (The Deciding Factor)
* **AWS Lambda**: AWS Lambda runs on a pay-as-you-go billing model down to the millisecond. For 2-5 users, the app will sit idle 99% of the time. You will likely pay **$0.00** for compute because your active execution time will fit easily within the AWS Free Tier (400,000 GB-seconds free per month).
* **AWS ECS (Fargate)**: Fargate requires at least one task running 24/7. To host Python running LangChain and FAISS, you need at least **1 vCPU and 2 GB Memory**, costing ~$15 - $20/month. Additionally, exposing an ECS service securely to HTTP clients requires an **Application Load Balancer (ALB)**, which costs a flat **~$20/month** on its own.

### 2. Cold Starts vs. Warm Responses
* **AWS Lambda (~480MB Image)**: When a request arrives after 15-30 minutes of inactivity, Lambda boots the container. For a ~480MB image, this "cold start" takes **3 to 5 seconds**. Once the container is booted, subsequent requests are processed in milliseconds (warm starts). For 2-5 users, a 3-second delay on the first paper generated in a session is generally acceptable.
* **AWS ECS**: Since the container runs 24/7, there are zero cold starts. Responses are instantaneous.

### 3. Architecture Compatibility
* The backend (`qplambda.py`) is already fully architected to be **stateless** (it retrieves FAISS vector stores dynamically from S3 and uploads generated PDFs to S3). This matches the Serverless paradigm perfectly.

---

## 🏆 Final Judgement & Recommendation

For **2-5 users**, **AWS Lambda** is the **most suitable, cost-effective, and practical method**.

### Rationale:
1. **Financial**: It is hard to justify spending **$40+/month** on AWS ECS + ALB for 2-5 users when AWS Lambda will cost **less than $0.50/month** (only S3 storage fees for the ECR image and PDFs).
2. **Minimal Maintenance**: You do not have to manage VPCs, subnets, target groups, or load balancer configurations.
3. **Optimized Image Size**: Since we optimized the dependencies (removed heavy packages like PyTorch and sentence-transformers) and got the Docker image down to **~480MB**, Lambda's cold starts will be extremely fast (typically under 4 seconds).
