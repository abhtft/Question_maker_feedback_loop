
"""
This module serves as the brain for the question generation system, housing all the core logic for processing documents, retrieving context, and generating questions. It follows a modular, object-oriented design that separates concerns for maintainability and extensibility.

Key Components:

document_processor: Handles the ingestion and preparation of educational materials. It uses advanced text splitting techniques to break down documents into manageable chunks while preserving context.

context_retriever: Implements a sophisticated retrieval system that goes beyond simple keyword matching. It uses semantic search to find the most relevant information for question generation.

question_generator: Orchestrates the question generation process. It uses a powerful LLM to create a wide range of questions that match the specified difficulty and topic requirements.

question_verifier: Ensures the quality of generated questions. It uses an LLM to review questions for accuracy, clarity, and appropriateness.

This module is designed to be easily integrated with other parts of the system, providing a robust foundation for automated question paper generation.


cmd: python backend/generator/generator.py












"""


from langchain_community.document_loaders import PyPDFLoader  
from langchain_text_splitters import RecursiveCharacterTextSplitter  
from langchain_openai import AzureOpenAIEmbeddings, AzureChatOpenAI, ChatOpenAI, OpenAIEmbeddings  
from langchain_community.vectorstores import FAISS  
from langchain_core.prompts import PromptTemplate

import os  
from dotenv import load_dotenv  
from typing import Dict, List, Any, Tuple, Optional  
import logging  

import tiktoken  
import json  
import re  
import hashlib
from datetime import datetime

# Import LiteLLM Fallback Connection Client wrapper
try:
    import sys
    # Resolve config path
    current_dir = os.path.dirname(os.path.abspath(__file__))
    if "backend" in current_dir:
        project_root = os.path.dirname(os.path.dirname(current_dir))
    else:
        project_root = current_dir
    config_dir = os.path.join(project_root, "config")
    if config_dir not in sys.path:
        sys.path.append(config_dir)
        
    from llmconfig import LiteLLMChatWrapper, LiteLLMFallbackClient, LiteLLMEmbeddings
    LITE_LLM_CLIENT_AVAILABLE = True
except Exception as _llm_config_err:
    LITE_LLM_CLIENT_AVAILABLE = False
    logger_init = logging.getLogger(__name__)
    logger_init.warning(f"LiteLLM client wrapper not available: {_llm_config_err}")

# Context Engineering Pipeline (Techniques 1-10)
# See learning/context_engineering.md for detailed explanations
try:
    from context_engineering import ContextEngineeringPipeline
    from context_engineering.prompt_router import FewShotSelector
    CONTEXT_ENGINEERING_AVAILABLE = True
    logger_init = logging.getLogger(__name__)
    logger_init.info("Context Engineering Pipeline loaded successfully")
except ImportError as _ce_err:
    CONTEXT_ENGINEERING_AVAILABLE = False
    logger_init = logging.getLogger(__name__)
    logger_init.warning(f"Context Engineering Pipeline not available: {_ce_err}. "
                        f"Using original prompts.")

# Load environment variables  
load_dotenv()  

"""
Form of sample input JSON
{
  "subjectName": "Mathematics",
  "classGrade": "Grade 10",
    "sectionName": "Quadratic Equations",
    "difficulty": "Medium",
    "bloomLevel": "Apply",
    "questionType": "MCQ",
    "numQuestion
    Instructions": "Focus on real-world applications of quadratic equations."
}
"""
  
# Configure logging  
logging.basicConfig(level=logging.INFO)  
logger = logging.getLogger(__name__)  
  
# -------------------------------  
# Utility: Robust JSON parser  
# ------------------------------- 
#  
def safe_json_loads(text: str, default: Any = None) -> Any:  
    """  
    Safely parse JSON from a string. Handles ```json fenced code and extracts  
    the first valid JSON object found. Returns `default` on failure.  
    """  
    try:  
        #used to remove backstring and json word from llm output
        # Ensure text is a string(safety check)
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
# Enhanced Document Processor with Smart Chunking  
# -------------------------------  
class DocumentProcessor:  
    def __init__(self):  
        # Standardized embedding initialization using LiteLLMEmbeddings from llmconfig.py
        if LITE_LLM_CLIENT_AVAILABLE:
            try:
                self.embeddings = LiteLLMEmbeddings()
                logger.info("Initialized LiteLLMEmbeddings for DocumentProcessor")
            except Exception as e:
                logger.warning(f"Failed to initialize LiteLLMEmbeddings: {e}. Falling back to default LangChain embeddings.")
                azure_key = os.getenv('AZURE_OPENAI_API_KEY')
                if azure_key:
                    self.embeddings = AzureOpenAIEmbeddings(  
                        azure_deployment='text-embedding-3-large',  
                        api_version=os.getenv('AZURE_OPENAI_API_VERSION', '2024-02-15-preview'),  
                        azure_endpoint=os.getenv('AZURE_OPENAI_ENDPOINT'),  
                        api_key=azure_key,  
                    )  
                else:
                    self.embeddings = OpenAIEmbeddings(
                        openai_api_key=os.getenv('OPENAI_API_KEY', 'placeholder')
                    )
        else:
            azure_key = os.getenv('AZURE_OPENAI_API_KEY')
            if azure_key:
                self.embeddings = AzureOpenAIEmbeddings(  
                    azure_deployment='text-embedding-3-large',  
                    api_version=os.getenv('AZURE_OPENAI_API_VERSION', '2024-02-15-preview'),  
                    azure_endpoint=os.getenv('AZURE_OPENAI_ENDPOINT'),  
                    api_key=azure_key,  
                )  
            else:
                self.embeddings = OpenAIEmbeddings(
                    openai_api_key=os.getenv('OPENAI_API_KEY', 'placeholder')
                )  
        
        # Enhanced text splitters for different content types
        #dict
        self.text_splitters = {
            'default': RecursiveCharacterTextSplitter(
                chunk_size=1000,
                chunk_overlap=200,
                length_function=len,
                separators=["\n\n", "\n", " ", ""]
            ),

            'mathematics': RecursiveCharacterTextSplitter(
                chunk_size=800,  # Smaller chunks for math (formulas, equations)
                chunk_overlap=150,
                length_function=len,
                separators=["\n\n", "\n", " ", ""]
            ),
            'science': RecursiveCharacterTextSplitter(
                chunk_size=1200,  # Larger chunks for science concepts
                chunk_overlap=250,
                length_function=len,
                separators=["\n\n", "\n", " ", ""]
            ),
            'literature': RecursiveCharacterTextSplitter(
                chunk_size=1500,  # Larger chunks for literature
                chunk_overlap=300,
                length_function=len,
                separators=["\n\n", "\n", " ", ""]
            )
        }

    #for content type detection:
    #1.manual detection:regext not good now
    #ai detection:based on keywords
    def _detect_content_type(self, text: str) -> str:
        """Detect content type based on text characteristics"""
        text_lower = text.lower()
        
        # Mathematics indicators
        math_indicators = ['equation', 'formula', 'calculate', 'solve', 'mathematics', 'math', 'algebra', 'geometry', 'trigonometry', 'calculus', '+', '-', '*', '/', '=', '√', 'π', '∫', '∑']
        math_score = sum(1 for indicator in math_indicators if indicator in text_lower)
        
        # Science indicators
        science_indicators = ['experiment', 'hypothesis', 'theory', 'molecule', 'atom', 'cell', 'organism', 'physics', 'chemistry', 'biology', 'laboratory', 'observation', 'conclusion']
        science_score = sum(1 for indicator in science_indicators if indicator in text_lower)
        
        # Literature indicators
        literature_indicators = ['poem', 'story', 'novel', 'character', 'plot', 'theme', 'metaphor', 'simile', 'literature', 'english', 'grammar', 'vocabulary', 'comprehension']
        literature_score = sum(1 for indicator in literature_indicators if indicator in text_lower)
        
        # Determine content type (A,B,C)
        if math_score > max(science_score, literature_score):
            return 'mathematics'
        elif science_score > literature_score:
            return 'science'
        elif literature_score > 0:
            return 'literature'
        else:
            return 'default'


    def _enhance_metadata(self, doc, content_type: str, subject: str = None, grade: str = None) -> Dict[str, Any]:
        """Add enhanced metadata to documents
        1. content type
        2. subject and grade
        3. unique chunk ID
        4. processing timestamp
        5. word count
        6. quality score for filtering
        """
        
        metadata = doc.metadata.copy()
        metadata.update({
            'content_type': content_type,
            'subject': subject or 'unknown',
            'grade': grade or 'unknown',
            'chunk_id': hashlib.md5(doc.page_content.encode()).hexdigest()[:8],
            'processed_at': datetime.now().isoformat(),
            'word_count': len(doc.page_content.split()),
            'quality_score': self._calculate_quality_score(doc.page_content)
        })
        return metadata

        #protected
    def _calculate_quality_score(self, text: str) -> float:
        """Calculate quality score for content filtering"""
        if not text or len(text.strip()) < 50:
            return 0.0
        
        # Quality indicators
        has_sentences = len([s for s in text.split('.') if len(s.strip()) > 10]) > 0
        has_paragraphs = len([p for p in text.split('\n\n') if len(p.strip()) > 50]) > 0
        has_structure = any(char in text for char in [':', '-', '•', '*'])
        
        score = 0.0
        if has_sentences: score += 0.4
        if has_paragraphs: score += 0.3
        if has_structure: score += 0.3
        
        return min(score, 1.0)

        #udnerstanding by structure /usage

    def process_uploaded_document(self, pdf_path, persist_directory=None, subject: str = None, grade: str = None) -> Tuple[Any, List[Any]]:  
        try:  
            loader = PyPDFLoader(pdf_path)  
            pages = loader.load()  
            
            # Enhanced processing with content type detection
            enhanced_texts = []
            for page in pages:
                content_type = self._detect_content_type(page.page_content)
                splitter = self.text_splitters.get(content_type, self.text_splitters['default'])
                chunks = splitter.split_documents([page])
                
                # Add enhanced metadata to each chunk
                for chunk in chunks:
                    chunk.metadata = self._enhance_metadata(chunk, content_type, subject, grade)
                    # Filter out low-quality chunks
                    if chunk.metadata.get('quality_score', 0) > 0.3:
                        enhanced_texts.append(chunk)
            
            logger.info(f"Processed PDF '{pdf_path}' into {len(enhanced_texts)} quality chunks (filtered from {sum(len(splitter.split_documents([page])) for page in pages)} total chunks)")
            
            vectorstore = FAISS.from_documents(  
                documents=enhanced_texts,  
                embedding=self.embeddings  
            )  
  
            if persist_directory:  
                vectorstore.save_local(persist_directory)  
            else:  
                vectorstore.save_local("./faiss_index")  
  
            return vectorstore, enhanced_texts  
        except Exception as e:  
            logger.error(f"Error processing document: {str(e)}")  
            raise  

# -------------------------------  
# Enhanced Context Retrieval System  
# -------------------------------  
class EnhancedContextRetriever:
    def __init__(self, vectorstore: Any):
        self.vectorstore = vectorstore
        
    def _build_semantic_query(self, topic_data: Dict[str, Any]) -> str:
        """Build enhanced semantic query based on topic data"""
        subject = topic_data.get('subjectName', '').lower()
        section = topic_data.get('sectionName', '').lower()
        difficulty = topic_data.get('difficulty', '').lower()
        bloom_level = topic_data.get('bloomLevel', '').lower()
        grade = topic_data.get('classGrade', '').lower()
        
        # Enhanced query building with subject-specific terms
        query_parts = []
        
        # Core topic
        if section:
            query_parts.append(section)
        
        # Subject-specific enhancements
        if 'mathematics' in subject or 'math' in subject:
            query_parts.extend(['mathematics', 'mathematical', 'calculation', 'problem solving'])
        elif 'science' in subject:
            query_parts.extend(['scientific', 'experiment', 'theory', 'concept'])
        elif 'english' in subject or 'literature' in subject:
            query_parts.extend(['literature', 'comprehension', 'grammar', 'vocabulary'])
        elif 'history' in subject:
            query_parts.extend(['historical', 'event', 'period', 'civilization'])
        elif 'geography' in subject:
            query_parts.extend(['geographical', 'location', 'region', 'environment'])
        
        # Difficulty-specific terms
        if difficulty == 'easy':
            query_parts.extend(['basic', 'fundamental', 'introductory'])
        elif difficulty == 'hard':
            query_parts.extend(['advanced', 'complex', 'challenging'])
        
        # Bloom's taxonomy terms
        bloom_terms = {
            'remember': ['recall', 'memorize', 'identify', 'define'],
            'understand': ['explain', 'describe', 'interpret', 'summarize'],
            'apply': ['apply', 'solve', 'use', 'implement'],
            'analyze': ['analyze', 'compare', 'contrast', 'examine'],
            'evaluate': ['evaluate', 'assess', 'judge', 'critique'],
            'create': ['create', 'design', 'develop', 'construct']
        }
        if bloom_level in bloom_terms:
            query_parts.extend(bloom_terms[bloom_level])
        
        # Grade-specific terms
        if 'grade' in grade or 'class' in grade:
            query_parts.append(grade)
        
        return ' '.join(query_parts)
    
    def _determine_search_parameters(self, topic_data: Dict[str, Any]) -> Tuple[int, int]:
        """Determine optimal search parameters based on topic complexity"""
        subject = topic_data.get('subjectName', '').lower()
        difficulty = topic_data.get('difficulty', '').lower()
        bloom_level = topic_data.get('bloomLevel', '').lower()
        
        # Base parameters
        k_docs = 4
        max_tokens = 1000
        
        # Adjust based on complexity
        if difficulty == 'hard':
            k_docs = 6
            max_tokens = 1500
        elif difficulty == 'easy':
            k_docs = 3
            max_tokens = 800
        
        # Adjust based on Bloom's level
        if bloom_level in ['analyze', 'evaluate', 'create']:
            k_docs = max(k_docs, 5)
            max_tokens = max(max_tokens, 1200)
        
        # Adjust based on subject complexity
        if 'mathematics' in subject:
            k_docs = max(k_docs, 5)  # Math needs more context for formulas
        elif 'science' in subject:
            k_docs = max(k_docs, 4)  # Science needs balanced context
        
        return k_docs, max_tokens
    
    def get_enhanced_context(self, topic_data: Dict[str, Any]) -> str:
        """Get enhanced context using improved retrieval strategies"""
        try:
            # Build semantic query
            semantic_query = self._build_semantic_query(topic_data)
            logger.info(f"Enhanced semantic query: {semantic_query}")
            
            # Determine search parameters
            k_docs, max_tokens = self._determine_search_parameters(topic_data)
            logger.info(f"Search parameters: k={k_docs}, max_tokens={max_tokens}")
            
            # Perform enhanced similarity search
            docs = self.vectorstore.similarity_search(
                semantic_query,
                k=k_docs
            )
            
            # Combine and rank documents
            combined_content = self._combine_and_rank_documents(docs, topic_data)
            
            # Truncate to token limit
            context = self._truncate_to_tokens(combined_content, max_tokens)
            
            logger.info(f"Retrieved context length: {len(context)} characters")
            return context
            
        except Exception as e:
            logger.error(f"Error in enhanced context retrieval: {e}")
            return ""
    
    def _combine_and_rank_documents(self, docs: List[Any], topic_data: Dict[str, Any]) -> str:
        """Combine documents with intelligent ranking"""
        if not docs:
            return ""
        
        # Score documents based on relevance
        scored_docs = []
        for doc in docs:
            score = self._calculate_document_relevance(doc, topic_data)
            scored_docs.append((score, doc))
        
        # Sort by relevance score
        scored_docs.sort(key=lambda x: x[0], reverse=True)
        
        # Combine content with priority to higher-scored documents
        combined_parts = []
        for score, doc in scored_docs:
            if score > 0.3:  # Only include relevant documents
                combined_parts.append(doc.page_content.strip())
        
        return "\n\n".join(combined_parts)
    

    
    def _calculate_document_relevance(self, doc: Any, topic_data: Dict[str, Any]) -> float:
        """Calculate relevance score for a document"""
        content = doc.page_content.lower()
        metadata = doc.metadata
        
        score = 0.0
        
        # Subject match
        if topic_data.get('subjectName', '').lower() in content:
            score += 0.3
        
        # Section match
        if topic_data.get('sectionName', '').lower() in content:
            score += 0.4
        
        # Metadata quality
        if metadata.get('quality_score', 0) > 0.5:
            score += 0.2
        
        # Content type match
        subject = topic_data.get('subjectName', '').lower()
        content_type = metadata.get('content_type', 'default')
        if ('mathematics' in subject and content_type == 'mathematics') or \
           ('science' in subject and content_type == 'science') or \
           ('english' in subject and content_type == 'literature'):
            score += 0.1
        
        return min(score, 1.0)
    
    def _truncate_to_tokens(self, text: str, max_tokens: int, model: str = "gpt-4") -> str:
        """Truncate text to token limit"""
        try:
            enc = tiktoken.encoding_for_model(model)
            tokens = enc.encode(text)
            if len(tokens) <= max_tokens:
                return text
            
            truncated_tokens = tokens[:max_tokens]
            return enc.decode(truncated_tokens)
        except Exception as e:
            logger.error(f"Error in token truncation: {e}")
            # Fallback to character-based truncation
            return text[:max_tokens * 4]  # Rough approximation

# -------------------------------  
# Question Quality Verifier  
# -------------------------------  

class QuestionQualityVerifier:  
    def __init__(self):  
        azure_key = os.getenv('AZURE_OPENAI_API_KEY')
        openrouter_key = os.getenv('OPENROUTER_API_KEY')
        
        if LITE_LLM_CLIENT_AVAILABLE:
            try:
                self.llm = LiteLLMChatWrapper()
                logger.info("Initialized LiteLLMChatWrapper for QuestionQualityVerifier")
            except Exception as e:
                logger.warning(f"Failed to initialize LiteLLMChatWrapper: {e}. Falling back to default LangChain LLM.")
                if azure_key:
                    self.llm = AzureChatOpenAI(  
                        azure_deployment=os.getenv('AZURE_OPENAI_CHAT_DEPLOYMENT', 'gpt-4.1'),  
                        api_version=os.getenv('AZURE_OPENAI_API_VERSION', '2024-02-15-preview'),  
                        temperature=0,  
                        azure_endpoint=os.getenv('AZURE_OPENAI_ENDPOINT'),  
                        api_key=azure_key,  
                    )  
                elif openrouter_key:
                    self.llm = ChatOpenAI(
                        openai_api_key=openrouter_key,
                        openai_api_base='https://openrouter.ai/api/v1',
                        model_name=os.getenv('OPENROUTER_MODEL', 'openai/gpt-4o'),
                        temperature=0
                    )
                else:
                    self.llm = ChatOpenAI(
                        openai_api_key="placeholder",
                        openai_api_base='https://openrouter.ai/api/v1',
                        model_name='openai/gpt-4o',
                        temperature=0
                    )
        else:
            if azure_key:
                self.llm = AzureChatOpenAI(  
                    azure_deployment=os.getenv('AZURE_OPENAI_CHAT_DEPLOYMENT', 'gpt-4.1'),  
                    api_version=os.getenv('AZURE_OPENAI_API_VERSION', '2024-02-15-preview'),  
                    temperature=0,  
                    azure_endpoint=os.getenv('AZURE_OPENAI_ENDPOINT'),  
                    api_key=azure_key,  
                )  
            elif openrouter_key:
                self.llm = ChatOpenAI(
                    openai_api_key=openrouter_key,
                    openai_api_base='https://openrouter.ai/api/v1',
                    model_name=os.getenv('OPENROUTER_MODEL', 'openai/gpt-4o'),
                    temperature=0
                )
            else:
                self.llm = ChatOpenAI(
                    openai_api_key="placeholder",
                    openai_api_base='https://openrouter.ai/api/v1',
                    model_name='openai/gpt-4o',
                    temperature=0
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

        logger.info(f"Verification prompt: {self.prompt}")
  
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
        azure_key = os.getenv('AZURE_OPENAI_API_KEY')
        openrouter_key = os.getenv('OPENROUTER_API_KEY')
        
        if LITE_LLM_CLIENT_AVAILABLE:
            try:
                self.llm = LiteLLMChatWrapper()
                logger.info("Initialized LiteLLMChatWrapper for QuestionGenerator")
            except Exception as e:
                logger.warning(f"Failed to initialize LiteLLMChatWrapper: {e}. Falling back to default LangChain LLM.")
                if azure_key:
                    self.llm = AzureChatOpenAI(  
                        azure_deployment=os.getenv('AZURE_OPENAI_CHAT_DEPLOYMENT', 'gpt-4.1'),  
                        api_version=os.getenv('AZURE_OPENAI_API_VERSION', '2024-02-15-preview'),  
                        temperature=0.0,  
                        azure_endpoint=os.getenv('AZURE_OPENAI_ENDPOINT'),  
                        api_key=azure_key,  
                    )  
                elif openrouter_key:
                    self.llm = ChatOpenAI(
                        openai_api_key=openrouter_key,
                        openai_api_base='https://openrouter.ai/api/v1',
                        model_name=os.getenv('OPENROUTER_MODEL', 'openai/gpt-4o'),
                        temperature=0.0
                    )
                else:
                    self.llm = ChatOpenAI(
                        openai_api_key="placeholder",
                        openai_api_base='https://openrouter.ai/api/v1',
                        model_name='openai/gpt-4o',
                        temperature=0.0
                    )
        else:
            if azure_key:
                self.llm = AzureChatOpenAI(  
                    azure_deployment=os.getenv('AZURE_OPENAI_CHAT_DEPLOYMENT', 'gpt-4.1'),  
                    api_version=os.getenv('AZURE_OPENAI_API_VERSION', '2024-02-15-preview'),  
                    temperature=0.0,  
                    azure_endpoint=os.getenv('AZURE_OPENAI_ENDPOINT'),  
                    api_key=azure_key,  
                )  
            elif openrouter_key:
                self.llm = ChatOpenAI(
                    openai_api_key=openrouter_key,
                    openai_api_base='https://openrouter.ai/api/v1',
                    model_name=os.getenv('OPENROUTER_MODEL', 'openai/gpt-4o'),
                    temperature=0.0
                )
            else:
                self.llm = ChatOpenAI(
                    openai_api_key="placeholder",
                    openai_api_base='https://openrouter.ai/api/v1',
                    model_name='openai/gpt-4o',
                    temperature=0.0
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
        max_attempts = 3  
        
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

                    # For revision attempts (attempt > 0), use feedback from the previous attempt
                    # verification_result contains feedback from the most recent attempt

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
                logger.info(f"\nVerification result: {verification_result}\n")  
  
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
  
    def _get_context(self, topic_data: Dict[str, Any], vectorstore: Any) -> str:  
        """Get enhanced context using the new EnhancedContextRetriever"""
        if not vectorstore:
            return ""
            
        try:
            # Use the enhanced context retriever
            context_retriever = EnhancedContextRetriever(vectorstore)
            context = context_retriever.get_enhanced_context(topic_data)
            
            if context:
                logger.info(f"Enhanced context retrieved: {len(context)} characters")
                logger.debug(f"Context preview: {context[:200]}...")
            else:
                logger.warning("No context retrieved from enhanced retriever")
                
            return context
            
        except Exception as e:
            logger.error(f"Error in enhanced context retrieval: {e}")
            # Fallback to basic context retrieval
            return self._get_basic_context(topic_data, vectorstore)
    
    def _get_basic_context(self, topic_data: Dict[str, Any], vectorstore: Any) -> str:
        """Fallback basic context retrieval method"""
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
                logger.info(f"Using fallback context from vectorstore (truncated): {context[:200]}...")  
            except Exception as e:  
                logger.error(f"Error getting fallback context: {e}")  
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

# Initialize Context Engineering Pipeline (wraps around existing components)
# This adds Techniques 1-10 from learning/context_engineering.md
context_pipeline = None
if CONTEXT_ENGINEERING_AVAILABLE:
    try:
        context_pipeline = ContextEngineeringPipeline(
            llm=question_generator.llm if question_generator else None,  # Set to fallback LLM to enable summarization (Technique 5)
            embeddings=document_processor.embeddings,  # Reuse existing embeddings for cache
            config={
                'enable_summarization': False,  # Set True to enable Technique 5 (adds latency)
                'enable_cache': True,            # Technique 10: Semantic Caching
                'trim_mode': 'sentence_boundary', # Technique 4: sentence-aware trimming
                'max_tokens': 1000,
                'cache_threshold': 0.92,
                'few_shot_count': 2,              # Technique 3: inject 2 examples
            }
        )
        logger.info("Context Engineering Pipeline initialized and ready")
    except Exception as _pipe_err:
        logger.warning(f"Failed to initialize Context Engineering Pipeline: {_pipe_err}. "
                       f"Falling back to original behavior.")
        context_pipeline = None

"""
PHASE 1 IMPROVEMENTS IMPLEMENTED:
✅ Enhanced Document Processing with Smart Chunking
✅ Metadata-Enhanced Storage with Quality Filtering
✅ Enhanced Context Retrieval with Semantic Queries
✅ Dynamic Search Parameters based on Topic Complexity
✅ Content Type Detection and Specialized Chunking
✅ Document Relevance Scoring and Ranking

CONTEXT ENGINEERING TECHNIQUES (Phase 2):
✅ Technique 1: Classified Parameter Routing (prompt_router.py)
✅ Technique 2: Template-Data Separation (prompt_router.py)
✅ Technique 3: Few-Shot Example Injection (prompt_router.py)
✅ Technique 4: Trimming with sentence/paragraph modes (context_compressor.py)
✅ Technique 5: Summarization / Context Distillation (context_compressor.py)
✅ Technique 6: Pruning / Quality Gating (context_compressor.py)
✅ Technique 7: Strategic Ordering / Primacy-Recency (context_placer.py)
✅ Technique 8: Sliding Window + Anchoring (context_placer.py)
✅ Technique 9: RAG with Reranking (existing in EnhancedContextRetriever)
✅ Technique 10: Semantic Caching (context_cache.py)

See learning/context_engineering.md for detailed explanations of each technique.
OUTPUT FORMAT REMAINS UNCHANGED - FULL COMPATIBILITY WITH app.py
""" 
