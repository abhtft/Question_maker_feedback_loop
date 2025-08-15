from langchain_community.document_loaders import PyPDFLoader  
from langchain_text_splitters import RecursiveCharacterTextSplitter  
from langchain_openai import AzureOpenAIEmbeddings, AzureChatOpenAI  
from langchain_community.vectorstores import FAISS  
from langchain_core.prompts import PromptTemplate  
import os  
from dotenv import load_dotenv  
from typing import Dict, List, Any, Tuple  
import logging  
import tiktoken  
import json  
import re  
  
# Load environment variables  
load_dotenv()  
  
# Configure logging  
logging.basicConfig(level=logging.INFO)  
logger = logging.getLogger(__name__)  
  
# -------------------------------  
# Utility: Robust JSON parser  
# -------------------------------  
def safe_json_loads(text: str, default: Any = None) -> Any:  
    """  
    Safely parse JSON from a string. Handles ```json fenced code and extracts  
    the first valid JSON object found. Returns `default` on failure.  
    """  
    try:  
        # Ensure text is a string
        if not isinstance(text, str):
            text = str(text)
            
        # Remove markdown fences  
        if text.strip().startswith("```"):  
            parts = text.strip().split("```")  
            if len(parts) >= 2:  
                text = parts[1]  
        # Remove leading 'json'  
        if text.strip().lower().startswith("json"):  
            text = text.strip()[4:]  
        text = text.strip()  
  
        # Try direct load  
        return json.loads(text)  
    except json.JSONDecodeError:  
        # Try regex extraction  
        match = re.search(r"\{[\s\S]*\}", text)  
        if match:  
            try:  
                return json.loads(match.group(0))  
            except json.JSONDecodeError as e:  
                logger.error(f"Regex JSON parse failed: {e}")  
        logger.error("Failed to parse JSON; returning default.")  
        return default  
  
  
# -------------------------------  
# Document Processor  
# -------------------------------  
class DocumentProcessor:  
    def __init__(self):  
        self.embeddings = AzureOpenAIEmbeddings(  
            azure_deployment='text-embedding-3-large',  
            api_version=os.getenv('AZURE_OPENAI_API_VERSION', '2024-02-15-preview'),  
            azure_endpoint=os.getenv('AZURE_OPENAI_ENDPOINT'),  
            api_key=os.getenv('AZURE_OPENAI_API_KEY'),  
        )  
        self.text_splitter = RecursiveCharacterTextSplitter(  
            chunk_size=1000,  
            chunk_overlap=200,  
            length_function=len,  
            separators=["\n\n", "\n", " ", ""]  
        )  
  
    def process_uploaded_document(self, pdf_path, persist_directory=None) -> Tuple[Any, List[Any]]:  
        try:  
            loader = PyPDFLoader(pdf_path)  
            pages = loader.load()  
            texts = self.text_splitter.split_documents(pages)  
  
            vectorstore = FAISS.from_documents(  
                documents=texts,  
                embedding=self.embeddings  
            )  
  
            if persist_directory:  
                vectorstore.save_local(persist_directory)  
            else:  
                vectorstore.save_local("./faiss_index")  
  
            logger.info(f"Processed PDF '{pdf_path}' into {len(texts)} chunks")  
            return vectorstore, texts  
        except Exception as e:  
            logger.error(f"Error processing document: {str(e)}")  
            raise  
  
  
# -------------------------------  
# Question Quality Verifier  
# -------------------------------  

class QuestionQualityVerifier:  
    def __init__(self):  
        self.llm = AzureChatOpenAI(  
            azure_deployment=os.getenv('AZURE_OPENAI_CHAT_DEPLOYMENT', 'gpt-4.1'),  
            api_version=os.getenv('AZURE_OPENAI_API_VERSION', '2024-02-15-preview'),  
            temperature=0,  
            azure_endpoint=os.getenv('AZURE_OPENAI_ENDPOINT'),  
            api_key=os.getenv('AZURE_OPENAI_API_KEY'),  
        )  
  
        # ✅ Fixed: Properly escaped curly braces for LangChain PromptTemplate
        self.verification_template = """  
You are an expert educational assessment evaluator with deep knowledge of Bloom's taxonomy, difficulty calibration, and subject-specific pedagogy.  
  
You will receive:  
- A set of generated questions  
- The intended subject, grade level, topic, difficulty, and Bloom's taxonomy level  
- The original context (learning material)  
  
**Question Details:**
Subject: {subject}
Grade: {class_grade}
Topic: {topic}
Difficulty: {difficulty}
Bloom's Level: {bloom_level}
Question Type: {question_type}

**Context:**
{context}

**Questions to Evaluate:**
{questions}

Your task:  
1. Evaluate the questions for:  
   - **Relevance**: Do they match the provided context and topic?  
   - **Difficulty Alignment**: Do they match the specified difficulty level?  
   - **Bloom's Taxonomy Alignment**: Do they match the specified cognitive level?  
   - **Subject & Grade Appropriateness**  
   - **Overall Quality**: Clarity, correctness, and completeness.  
  
2. Provide scores (0–100) for each category.  
3. Identify **specific issues** (if any).  
4. Provide **improvement suggestions**.  
5. Give an **overall verdict**: ACCEPTED or REJECTED.  
6. Output must be valid JSON with the exact schema:  
  
{{
  "overall_verdict": "ACCEPTED" | "REJECTED",  
  "confidence_score": <integer>,  
  "detailed_feedback": {{
    "relevance_score": <integer>,  
    "difficulty_alignment": <integer>,  
    "bloom_taxonomy_alignment": <integer>,  
    "subject_grade_alignment": <integer>,  
    "overall_quality": <integer>  
  }},  
  "specific_issues": ["..."],  
  "improvement_suggestions": ["..."]  
}}  
  
Do not include any text outside the JSON.  
"""  
  
        self.prompt = PromptTemplate(  
            input_variables=[  
                "context", "questions", "subject", "class_grade", "topic",  
                "difficulty", "bloom_level", "question_type"  
            ],  
            template=self.verification_template  
        )  
  
        self.chain = self.prompt | self.llm  
  
    def verify_questions(self, questions: Dict[str, Any], topic_data: Dict[str, Any], context: str) -> Dict[str, Any]:  
        try:  
            # Ensure topic_data is a dictionary and has required keys
            if not isinstance(topic_data, dict):
                logger.error(f"topic_data is not a dictionary: {type(topic_data)}")
                topic_data = {}
                
            questions_text = json.dumps(questions, indent=2)  
            response = self.chain.invoke({  
                "context": context,  
                "questions": questions_text,  
                "subject": topic_data.get('subjectName', 'Unknown'),  
                "class_grade": topic_data.get('classGrade', 'Unknown'),  
                "topic": topic_data.get('sectionName', 'Unknown'),  
                "difficulty": topic_data.get('difficulty', 'Unknown'),  
                "bloom_level": topic_data.get('bloomLevel', 'Unknown'),  
                "question_type": topic_data.get('questionType', 'Unknown')  
            })  
  
            llm_output = response.content if hasattr(response, 'content') else str(response)  
            logger.debug(f"Raw verifier output:\n{llm_output}")  
  
            verification_result = safe_json_loads(llm_output, default={})  
  
            # ✅ Always return a dict  
            if not isinstance(verification_result, dict):  
                logger.warning("Verifier returned non-dict; using fallback ACCEPTED result.")  
                verification_result = {  
                    "overall_verdict": "ACCEPTED",  
                    "confidence_score": 80,  
                    "detailed_feedback": {  
                        "relevance_score": 80,  
                        "difficulty_alignment": 80,  
                        "bloom_taxonomy_alignment": 80,  
                        "subject_grade_alignment": 80,  
                        "overall_quality": 80  
                    },  
                    "specific_issues": [],  
                    "improvement_suggestions": []  
                }  
  
            logger.info(f"Verification result: {verification_result.get('overall_verdict', 'UNKNOWN')}")  
            return verification_result  
  
        except Exception as e:  
            logger.error(f"Error in question verification: {e}")  
            return {  
                "overall_verdict": "ACCEPTED",  
                "confidence_score": 70,  
                "detailed_feedback": {  
                    "relevance_score": 70,  
                    "difficulty_alignment": 70,  
                    "bloom_taxonomy_alignment": 70,  
                    "subject_grade_alignment": 70,  
                    "overall_quality": 70  
                },  
                "specific_issues": ["Verification process encountered an error"],  
                "improvement_suggestions": ["Consider manual review of generated questions"]  
            }  

# -------------------------------  
# Question Generator  
# -------------------------------  
class QuestionGenerator:  
    def __init__(self):  
        self.llm = AzureChatOpenAI(  
            azure_deployment=os.getenv('AZURE_OPENAI_CHAT_DEPLOYMENT', 'gpt-4.1'),  
            api_version=os.getenv('AZURE_OPENAI_API_VERSION', '2024-02-15-preview'),  
            temperature=0.0,  # Lower temp for more predictable JSON  
            azure_endpoint=os.getenv('AZURE_OPENAI_ENDPOINT'),  
            api_key=os.getenv('AZURE_OPENAI_API_KEY'),  
        )  
  
        # ======== Your Original Question Prompt ========  
        self.question_template = """  
You are a highly skilled educational question generator.   
Generate exactly {num_questions} {question_type} questions for:  
Subject: {subject}  
Grade: {class_grade}  
Topic: {topic}  
Difficulty: {difficulty}  
Bloom's Level: {bloom_level}  
  
Context:  
{context}  
  
Additional Instructions:  
{instructions}  
  
🎯 Output Format (Strict JSON):
{{
"questions": [
    {{
    "question": "Your question text here.",
    "options": ["Option A", "Option B", "Option C", "Option D"],
    "answer": "Correct option here",
    "explanation": "Detailed explanation with reasoning."
    }}
]
}} 
  
output must not be in backticks and must be in json format.Please not write just json.
correct json format is given above.




Rules:  
- Each question must have exactly 4 options.  
- The answer must match one of the options exactly.  
- The explanation must justify why the answer is correct.  
- No extra text outside JSON.  
"""  
  
        # ======== Your Original Revision Prompt ========  
        self.revision_template = """  
You are a highly skilled educational question generator.  
You previously generated questions that did not meet quality requirements.  
  
Context:  
{context}  
  
Original Issues:  
{quality_issues}  
  
Suggestions:  
{improvement_suggestions}  
  
Specific Improvements:  
{specific_improvements}  
  
Generate exactly {num_questions} {question_type} questions for:  
Subject: {subject}  
Grade: {class_grade}  
Topic: {topic}  
Difficulty: {difficulty}  
Bloom's Level: {bloom_level}  
  
Instructions:  
{instructions}  
  
🎯 Output Format (Strict JSON):
{{
"questions": [
    {{
    "question": "Your question text here.",
    "options": ["Option A", "Option B", "Option C", "Option D"],
    "answer": "Correct option here",
    "explanation": "Detailed explanation with reasoning."
    }}
]
}} 
  
output must not be in backticks and must be in json format.Please not write just json.
correct json format is given above.

"""  
  
        self.prompt = PromptTemplate(  
            input_variables=[  
                "context", "num_questions", "question_type", "subject",  
                "class_grade", "topic", "difficulty", "bloom_level", "instructions"  
            ],  
            template=self.question_template  
        )  
  
        self.revision_prompt = PromptTemplate(  
            input_variables=[  
                "context", "num_questions", "question_type", "subject",  
                "class_grade", "topic", "difficulty", "bloom_level", "instructions",  
                "quality_issues", "improvement_suggestions", "specific_improvements"  
            ],  
            template=self.revision_template  
        )  
  
        self.chain = self.prompt | self.llm  
        self.revision_chain = self.revision_prompt | self.llm  
  
    def generate_questions(self, topic_data: Dict[str, Any], vectorstore: Any, verifier: QuestionQualityVerifier) -> Dict[str, Any]:  
        max_attempts = 2  
        
        # Ensure topic_data is a dictionary
        if not isinstance(topic_data, dict):
            logger.error(f"topic_data is not a dictionary: {type(topic_data)}")
            raise ValueError("topic_data must be a dictionary")
            
        context = self._get_context(topic_data, vectorstore)  
        verification_result = None  # Prevents unbound variable error  
  
        for attempt in range(max_attempts):  
            try:  
                logger.info(f"Question generation attempt {attempt + 1}/{max_attempts}")  
  
                if attempt == 0:  
                    response = self.chain.invoke({  
                        "context": context,  
                        "num_questions": topic_data.get('numQuestions', 1),  
                        "question_type": topic_data.get('questionType', 'MCQ'),  
                        "subject": topic_data.get('subjectName', 'Unknown'),  
                        "class_grade": topic_data.get('classGrade', 'Unknown'),  
                        "topic": topic_data.get('sectionName', 'Unknown'),  
                        "difficulty": topic_data.get('difficulty', 'Medium'),  
                        "bloom_level": topic_data.get('bloomLevel', 'Remember'),  
                        "instructions": topic_data.get('additionalInstructions', '')  
                    })  
                else:  
                    quality_issues = self._format_issues(verification_result.get('specific_issues', [])) if verification_result else "Previous output was not valid JSON or missing required fields."  
                    improvement_suggestions = self._format_suggestions(verification_result.get('improvement_suggestions', [])) if verification_result else "Ensure output strictly follows the JSON schema."  
                    specific_improvements = self._format_improvements(verification_result) if verification_result else "Return only JSON with the required fields."  
  
                    response = self.revision_chain.invoke({  
                        "context": context,  
                        "num_questions": topic_data.get('numQuestions', 1),  
                        "question_type": topic_data.get('questionType', 'MCQ'),  
                        "subject": topic_data.get('subjectName', 'Unknown'),  
                        "class_grade": topic_data.get('classGrade', 'Unknown'),  
                        "topic": topic_data.get('sectionName', 'Unknown'),  
                        "difficulty": topic_data.get('difficulty', 'Medium'),  
                        "bloom_level": topic_data.get('bloomLevel', 'Remember'),  
                        "instructions": topic_data.get('additionalInstructions', ''),  
                        "quality_issues": quality_issues,  
                        "improvement_suggestions": improvement_suggestions,  
                        "specific_improvements": specific_improvements  
                    })  
  
                result = self._parse_llm_response(response)  
                verification_result = verifier.verify_questions(result, topic_data, context)  
  
                if verification_result['overall_verdict'] == 'ACCEPTED':  
                    logger.info(f"Questions accepted on attempt {attempt + 1}")  
                    return {  
                        'questions': result,  
                        'verification_result': verification_result,  
                        'attempts_used': attempt + 1  
                    }  
                else:  
                    logger.info(f"Questions rejected on attempt {attempt + 1}, preparing for revision")  
                    if attempt == max_attempts - 1:  
                        logger.warning("Maximum attempts reached, returning questions despite quality issues")  
                        return {  
                            'questions': result,  
                            'verification_result': verification_result,  
                            'attempts_used': attempt + 1,  
                            'warning': 'Maximum revision attempts reached'  
                        }  
  
            except Exception as e:  
                logger.error(f"Error in attempt {attempt + 1}: {e}")  
                if attempt == max_attempts - 1:  
                    raise  
  
        raise Exception("Failed to generate questions after maximum attempts")  
  
    def _get_context( self, topic_data: Dict[str, Any], vectorstore: Any) -> str:  
        def truncate_to_tokens(text: str, max_tokens: int = 4000, model: str = "gpt-4") -> str:  
            enc = tiktoken.encoding_for_model(model)  
            tokens = enc.encode(text)  
            truncated_tokens = tokens[:max_tokens]  
            return enc.decode(truncated_tokens)  

        context = ""  
        if vectorstore:  
            try:  
                # Safe access to topic_data keys
                subject = topic_data.get('subjectName', '')
                section = topic_data.get('sectionName', '')
                search_query = f"{subject} {section}".strip()
                
                if not search_query:
                    search_query = "general content"
                    
                docs = vectorstore.similarity_search(  
                    search_query,  
                    k=4  
                )  
                raw_context = "\n".join(doc.page_content.strip() for doc in docs)  
                context = truncate_to_tokens(raw_context, max_tokens=1000, model="gpt-4")  
                logger.info(f"Using context from vectorstore (truncated): {context[:200]}...")  
            except Exception as e:  
                logger.error(f"Error getting context: {e}")  
        return context  
  
    def _parse_llm_response(self, response: Any) -> Dict[str, Any]:  
        llm_output = response.content if hasattr(response, 'content') else str(response)  
        logger.info(f"Raw LLM output: {llm_output}")  
  
        # Ensure llm_output is a string
        if not isinstance(llm_output, str):
            llm_output = str(llm_output)
        
        result = safe_json_loads(llm_output, default=None)  
        if not isinstance(result, dict) or 'questions' not in result:  
            raise ValueError("Invalid response format: missing 'questions' key or not a dict")  
  
        if not isinstance(result['questions'], list):  
            raise ValueError("'questions' must be a list")  
  
        for i, q in enumerate(result['questions']):  
            if not isinstance(q, dict):  
                raise ValueError(f"Question {i} is not a dictionary")  
            required_fields = ['question', 'options', 'answer', 'explanation']  
            missing_fields = [field for field in required_fields if field not in q]  
            if missing_fields:  
                raise ValueError(f"Question {i} missing fields: {missing_fields}")  
            if not isinstance(q['options'], list) or len(q['options']) != 4:  
                raise ValueError(f"Question {i} must have exactly 4 options")  
            if q['answer'] not in q['options']:  
                raise ValueError(f"Question {i} answer must be one of the options")  
  
        return result  
  
    def _format_issues(self, issues: List[str]) -> str:  
        return "\n".join([f"- {issue}" for issue in issues]) if issues else "No specific issues identified"  
  
    def _format_suggestions(self, suggestions: List[str]) -> str:  
        return "\n".join([f"- {s}" for s in suggestions]) if suggestions else "No specific suggestions provided"  
  
    def _format_improvements(self, verification_result: Dict[str, Any]) -> str:  
        # Ensure verification_result is a dictionary
        if not isinstance(verification_result, dict):
            return "No specific improvements required"
            
        feedback = verification_result.get('detailed_feedback', {})  
        
        # Ensure feedback is a dictionary
        if not isinstance(feedback, dict):
            return "No specific improvements required"
            
        improvements = []  
        if feedback.get('relevance_score', 100) < 70:  
            improvements.append("Improve relevance to the provided context")  
        if feedback.get('difficulty_alignment', 100) < 70:  
            improvements.append("Better align with the specified difficulty level")  
        if feedback.get('bloom_taxonomy_alignment', 100) < 70:  
            improvements.append("Better align with the specified Bloom's taxonomy level")  
        if feedback.get('subject_grade_alignment', 100) < 70:  
            improvements.append("Make questions more appropriate for the subject and grade level")  
        if feedback.get('overall_quality', 100) < 70:  
            improvements.append("Improve overall question quality and clarity")  
        return "\n".join([f"- {improvement}" for improvement in improvements]) if improvements else "No specific improvements required"  
  
  
# -------------------------------  
# Initialize components  
# -------------------------------  
document_processor = DocumentProcessor()  
question_generator = QuestionGenerator()  
question_verifier = QuestionQualityVerifier()  



#prompt enhancement
#knowledge base
#how to find to the right knowledge base
#prompt enhancer to use the right knowledge base(close match),enhance the prompt to use the right knowledge base.


#research paper
#Iso standard
#personal DeprecationWarning
#presntation
#testing vedio
# (image ,direction oriented,)
# naming,mat property...
# lamhauge



#copilot 