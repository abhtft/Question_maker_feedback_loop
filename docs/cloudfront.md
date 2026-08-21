Congratulations! 🎉

You've successfully deployed your frontend using **Amazon S3 + CloudFront**, which is the standard architecture used by many production web applications. Here's a concise document you can keep as your deployment notes.

---

# AWS Frontend Deployment Guide (S3 + CloudFront)

## Final Architecture

```text
                User
                  │
                  ▼
        CloudFront Distribution
                  │
                  ▼
            Amazon S3 Bucket
                  │
      ┌───────────┴───────────┐
      ▼                       ▼
  index.html             CSS / JS / Assets
```

---

# Step 1: Build the Frontend

For React:

```bash
npm install
npm run build
```

The build folder will contain files like:

```
build/
dist/

├── index.html
├── assets/
├── css/
├── js/
```

---

# Step 2: Create S3 Bucket

Create a bucket.

Example:

```
staticqp
```

---

# Step 3: Upload Files

Upload all build files.

Example:

```
Bucket

├── index.html
├── assets/
├── css/
├── js/
├── store.svg
```

Ensure **index.html is in the root**, not inside another folder.

---

# Step 4: (Optional) Enable Static Website Hosting

Go to:

```
S3
↓

Bucket

↓

Properties

↓

Static Website Hosting
```

Enable:

```
Index Document

index.html
```

> If using CloudFront with **Origin Access Control (OAC)**, static website hosting is optional. The recommended production approach is to use the **S3 bucket endpoint**, not the website endpoint.

---

# Step 5: Create CloudFront Distribution

Navigate to:

```
CloudFront

↓

Create Distribution
```

Configure:

## Origin Type

```
Amazon S3
```

---

## Origin Domain

Select:

```
staticqp.s3.us-east-1.amazonaws.com
```

**Do not choose the website endpoint** when using OAC.

---

## Origin Path

Leave blank.

```
Origin Path

(empty)
```

Do **not** enter:

```
index.html
```

Origin Path is only used if your files are inside a folder.

Example:

```
Bucket

frontend/

    index.html
```

Then Origin Path would be:

```
/frontend
```

---

## Origin Access

Choose:

```
Origin Access Control (Recommended)
```

Create a new OAC if needed.

---

# Step 6: Bucket Policy

CloudFront requires permission to read the bucket.

Example policy:

```json
{
  "Effect": "Allow",
  "Principal": {
    "Service": "cloudfront.amazonaws.com"
  },
  "Action": "s3:GetObject",
  "Resource": "arn:aws:s3:::YOUR_BUCKET/*",
  "Condition": {
    "ArnLike": {
      "AWS:SourceArn": "arn:aws:cloudfront::<ACCOUNT_ID>:distribution/<DISTRIBUTION_ID>"
    }
  }
}
```

Your bucket policy was already correct.

---

# Step 7: Default Root Object (Important)

Go to:

```
CloudFront

↓

General

↓

Edit
```

Set:

```
Default Root Object

index.html
```

Without this, opening:

```
https://xxxx.cloudfront.net
```

may fail because CloudFront doesn't know which file to return.

---

# Step 8: Deploy

Wait until the distribution status changes to:

```
Deployed
```

Usually:

```
5–15 minutes
```

---

# Step 9: Test

CloudFront URL:

```
https://xxxxxxxx.cloudfront.net
```

If everything is configured correctly, your frontend should load.

---

# Step 10: Updating the Website

When you upload new files:

```
S3

↓

Upload

↓

Overwrite existing files
```

Then clear CloudFront's cache.

Go to:

```
CloudFront

↓

Invalidations

↓

Create Invalidation
```

Enter:

```
/*
```

Wait until the invalidation completes.

---

# Common Errors

## 403 Access Denied

Possible causes:

* Bucket policy missing
* OAC not configured
* CloudFront cannot access S3
* Default Root Object not configured

---

## CSS/JS Not Loading

Usually caused by:

* Wrong asset paths
* Incorrect React build configuration
* Files uploaded to the wrong folder

---

## 404 Error

Usually:

* `index.html` missing
* Wrong object path
* Incorrect Origin Path

---

## Website Not Updating

Reason:

CloudFront is serving cached files.

Solution:

```
Create Invalidation

↓

/*
```

---

# Best Practices

✅ Keep `index.html` in the bucket root.

✅ Use **Origin Access Control (OAC)** instead of making the bucket public.

✅ Keep **Block Public Access** enabled when using OAC.

✅ Set **Default Root Object** to `index.html`.

✅ Use **CloudFront** instead of accessing S3 directly.

---

# Production Architecture

```
User
   │
   ▼
CloudFront
   │
   ▼
S3 (React Frontend)
   │
   ▼
API Gateway
   │
   ▼
Lambda
   │
   ▼
DynamoDB / Bedrock / S3
```

This is a modern **serverless architecture** used by many AWS-hosted web applications.

---

# What You Learned

* ✅ Hosting static websites on Amazon S3
* ✅ Creating and configuring a CloudFront distribution
* ✅ Understanding Origin Access Control (OAC)
* ✅ Writing and using an S3 bucket policy for CloudFront
* ✅ Configuring the Default Root Object
* ✅ Understanding Origin Path
* ✅ CloudFront cache invalidation
* ✅ Troubleshooting 403 Access Denied errors

## Suggested Next Learning Path

Since your goal is to understand the complete flow from frontend to backend, I recommend this sequence:

1. **S3 + CloudFront** ✅ *(Completed)*
2. **API Gateway (HTTP API)**
3. **Lambda (Python)**
4. **Connect React → API Gateway → Lambda**
5. **Lambda → DynamoDB**
6. **Lambda → Amazon Bedrock**
7. **Authentication (Amazon Cognito or JWT)**
8. **Deploy the same backend on EC2 behind an ALB** to understand the differences between serverless and traditional architectures.

By the end of this roadmap, you'll understand both major AWS deployment patterns used in production.
