# Question Generation Workflow with Quality Verification

## 📊 Complete System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           DOCUMENT PROCESSING PHASE                          │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        DocumentProcessor Class                              │
├─────────────────────────────────────────────────────────────────────────────┤
│ 1. Load PDF using PyPDFLoader                                               │
│ 2. Split into chunks using RecursiveCharacterTextSplitter                   │
│ 3. Create FAISS vectorstore with Azure OpenAI Embeddings                   │
│ 4. Save vectorstore locally                                                 │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    QUESTION GENERATION & VERIFICATION PHASE                 │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    QuestionGenerator.generate_questions()                   │
│                              MAX_ATTEMPTS = 2                              │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           ATTEMPT LOOP START                                │
│                        ┌─────────────────────┐                             │
│                        │   ATTEMPT COUNTER   │                             │
│                        │   attempt = 0       │                             │
│                        └─────────────────────┘                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        CONTEXT EXTRACTION                                   │
│                    _get_context() Method                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│ 1. Perform similarity search on vectorstore                                 │
│    Query: f"{subjectName} {sectionName}"                                   │
│ 2. Retrieve top 4 relevant document chunks                                 │
│ 3. Truncate to 1000 tokens using tiktoken                                  │
│ 4. Return combined context string                                          │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    QUESTION GENERATION DECISION                             │
│                        ┌─────────────────┐                                 │
│                        │   attempt == 0? │                                 │
│                        └─────────────────┘                                 │
│                                │                                            │
│                    ┌───────────┴───────────┐                               │
│                    ▼                       ▼                               │
│        ┌─────────────────────┐   ┌─────────────────────┐                   │
│        │   FIRST ATTEMPT     │   │   REVISION ATTEMPT  │                   │
│        │  Original Template  │   │  Revision Template  │                   │
│        └─────────────────────┘   └─────────────────────┘                   │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    LLM CHAIN INVOCATION                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│ Input Parameters:                                                           │
│ • context: Extracted document chunks                                        │
│ • num_questions: Number of questions to generate                            │
│ • question_type: MCQ, Essay, etc.                                          │
│ • subject: Subject name                                                    │
│ • class_grade: Grade/class level                                           │
│ • topic: Section/topic name                                                │
│ • difficulty: Easy, Medium, Hard                                           │
│ • bloom_level: Remember, Understand, Apply, etc.                          │
│ • instructions: Additional educator instructions                           │
│ • [REVISION ONLY] quality_issues, improvement_suggestions, etc.            │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    RESPONSE PARSING & VALIDATION                            │
│                    _parse_llm_response() Method                             │
├─────────────────────────────────────────────────────────────────────────────┤
│ 1. Clean JSON response (remove markdown, code blocks)                      │
│ 2. Parse JSON using json.loads()                                           │
│ 3. Validate response structure:                                            │
│    • Check for 'questions' key                                             │
│    • Verify 'questions' is a list                                          │
│ 4. Validate each question:                                                 │
│    • Required fields: question, options, answer, explanation               │
│    • Exactly 4 options for MCQs                                           │
│    • Answer must be one of the options                                     │
│ 5. Return validated question structure                                     │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    QUALITY VERIFICATION PHASE                               │
│                QuestionQualityVerifier.verify_questions()                   │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    VERIFICATION LLM INVOCATION                              │
├─────────────────────────────────────────────────────────────────────────────┤
│ Input to Verification LLM:                                                  │
│ • Generated questions (JSON format)                                        │
│ • Original topic parameters                                                │
│ • Context used for generation                                              │
│                                                                             │
│ Evaluation Criteria:                                                        │
│ 1. Relevance Score (0-100)                                                 │
│ 2. Difficulty Alignment (0-100)                                            │
│ 3. Bloom's Taxonomy Alignment (0-100)                                      │
│ 4. Subject/Grade Alignment (0-100)                                         │
│ 5. Overall Quality (0-100)                                                 │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    VERIFICATION RESULT PARSING                              │
├─────────────────────────────────────────────────────────────────────────────┤
│ Expected JSON Response:                                                     │
│ {                                                                           │
│   "overall_verdict": "ACCEPTED" | "REJECTED",                              │
│   "confidence_score": 0-100,                                               │
│   "detailed_feedback": {                                                   │
│     "relevance_score": 0-100,                                              │
│     "difficulty_alignment": 0-100,                                         │
│     "bloom_taxonomy_alignment": 0-100,                                     │
│     "subject_grade_alignment": 0-100,                                      │
│     "overall_quality": 0-100                                               │
│   },                                                                        │
│   "specific_issues": ["list of problems"],                                 │
│   "improvement_suggestions": ["suggestions"]                               │
│ }                                                                           │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    VERDICT DECISION POINT                                   │
│                        ┌─────────────────┐                                 │
│                        │ verdict ==      │                                 │
│                        │ "ACCEPTED"?     │                                 │
│                        └─────────────────┘                                 │
│                                │                                            │
│                    ┌───────────┴───────────┐                               │
│                    ▼                       ▼                               │
│        ┌─────────────────────┐   ┌─────────────────────┐                   │
│        │   SUCCESS PATH      │   │   REVISION PATH     │                   │
│        │ Return Questions    │   │ Check Attempt Limit │                   │
│        │ + Verification      │   │                     │                   │
│        │ + Attempt Count     │   │                     │                   │
│        └─────────────────────┘   └─────────────────────┘                   │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    REVISION PATH DECISION                                   │
│                        ┌─────────────────┐                                 │
│                        │ attempt ==      │                                 │
│                        │ MAX_ATTEMPTS-1? │                                 │
│                        └─────────────────┘                                 │
│                                │                                            │
│                    ┌───────────┴───────────┐                               │
│                    ▼                       ▼                               │
│        ┌─────────────────────┐   ┌─────────────────────┐                   │
│        │   CONTINUE LOOP     │   │   MAX ATTEMPTS      │                   │
│        │ attempt++           │   │ REACHED             │                   │
│        │ Prepare feedback    │   │ Return with Warning │                   │
│        │ for next attempt    │   │                     │                   │
│        └─────────────────────┘   └─────────────────────┘                   │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    FEEDBACK PREPARATION (for revision)                      │
│                    Helper Methods:                                          │
├─────────────────────────────────────────────────────────────────────────────┤
│ _format_issues():                                                           │
│ • Convert specific_issues list to bullet points                            │
│                                                                             │
│ _format_suggestions():                                                      │
│ • Convert improvement_suggestions to bullet points                         │
│                                                                             │
│ _format_improvements():                                                     │
│ • Analyze detailed_feedback scores                                         │
│ • Generate specific improvement instructions                                │
│ • Focus on areas scoring below 70                                          │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    FINAL OUTPUT STRUCTURE                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│ Success Case:                                                               │
│ {                                                                           │
│   "questions": { /* validated question structure */ },                     │
│   "verification_result": { /* verification feedback */ },                  │
│   "attempts_used": 1 or 2                                                  │
│ }                                                                           │
│                                                                             │
│ Max Attempts Reached:                                                       │
│ {                                                                           │
│   "questions": { /* last generated questions */ },                         │
│   "verification_result": { /* verification feedback */ },                  │
│   "attempts_used": 2,                                                      │
│   "warning": "Maximum revision attempts reached"                           │
│ }                                                                           │
└─────────────────────────────────────────────────────────────────────────────┘

## 🔄 Detailed Flow Control

### **Attempt Loop Logic:**
```
START → attempt = 0
  ↓
attempt < MAX_ATTEMPTS (2)?
  ↓ YES
Generate Questions
  ↓
Verify Quality
  ↓
ACCEPTED?
  ↓ YES
RETURN SUCCESS
  ↓ NO
attempt == MAX_ATTEMPTS-1?
  ↓ YES
RETURN WITH WARNING
  ↓ NO
attempt++
  ↓
Prepare Revision Feedback
  ↓
GOTO START
```

### **Error Handling Points:**
1. **Document Processing Errors**: Log and raise exception
2. **Context Extraction Errors**: Continue with empty context
3. **LLM Response Parsing Errors**: Try regex extraction, then raise
4. **Verification JSON Errors**: Use fallback accepted result
5. **Verification Process Errors**: Return default accepted result

### **Quality Thresholds:**
- **ACCEPTED**: All criteria score 70+ and no major issues
- **REJECTED**: Any criterion scores below 60 or major issues present
- **Confidence Score**: 0-100 scale for overall verification confidence

## 🎯 Key Design Principles

1. **Fail-Safe Operation**: System continues even if verification fails
2. **Maximum Efficiency**: Limited to 2 attempts to prevent infinite loops
3. **Detailed Feedback**: Specific, actionable improvement suggestions
4. **Comprehensive Logging**: Full audit trail for debugging
5. **Graceful Degradation**: Returns questions even if quality standards aren't fully met

This workflow ensures robust, quality-controlled question generation with intelligent feedback loops while maintaining system reliability and performance.
