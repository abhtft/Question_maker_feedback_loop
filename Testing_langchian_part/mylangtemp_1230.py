from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_community.vectorstores import FAISS
from langchain.chains import LLMChain
from langchain_core.prompts import PromptTemplate
import os    
from dotenv import load_dotenv
from typing import Dict, List, Any, Optional, Tuple
import logging
import json
import re

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DocumentProcessor:
    def __init__(self):
        self.embeddings = OpenAIEmbeddings()
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

class QuestionGenerator:
    def __init__(self):
        self.llm = ChatOpenAI(
            model="gpt-4o",
            temperature=0.5
        )

        self.question_template = """
        You are an expert educational question generator.

        Create {num_questions} {question_type} questions for:
        Subject: {subject}
        Class: {class_grade}
        Topic: {topic}
        Difficulty: {difficulty}
        Bloom's Level: {bloom_level}

        Context: {context}

        Additional Instructions: {instructions}
        Use correct mathematical symbols:
        - Use '^' for exponents (e.g., write 10^3 instead of "10 to the power of 3")
        - Use '*' for multiplication
        - Use '/' for division
        - Avoid overly verbose expressions

        Requirements:
        1. Questions must be clear and unambiguous
        2. For MCQs, provide exactly 4 options
        3. Include detailed explanations
        4. Match the specified difficulty level
        5. Test understanding at the specified Bloom's level

        Return the response in this exact JSON format:
        {{
            "questions": [
                {{
                    "question": "Question text here ",
                    "options": ["Option A", "Option B", "Option C", "Option D"],
                    "answer": "Correct option here",
                    "explanation": "Detailed explanation here"
                }}
            ]
        }}
        """
        
        self.prompt = PromptTemplate(
            input_variables=[
                "context", "num_questions", "question_type", "subject",
                "class_grade", "topic", "difficulty", "bloom_level", "instructions"
            ],
            template=self.question_template
        )
        
        self.chain = LLMChain(llm=self.llm, prompt=self.prompt)
    
    def generate_questions(self, topic_data: Dict[str, Any], vectorstore: Any) -> Dict[str, Any]:
        try:
            # Get context from vectorstore
            context = ""
            if vectorstore:
                try:
                    docs = vectorstore.similarity_search(
                        f"{topic_data['subjectName']} {topic_data['sectionName']}",
                        k=3
                    )
                    context = "\n".join(doc.page_content for doc in docs)
                    logger.info(f"Using context from vectorstore: {context[:100]}...")
                except Exception as e:
                    logger.error(f"Error getting context: {e}")
            
            # Generate questions
            response = self.chain.invoke({
                "context": context,
                "num_questions": topic_data['numQuestions'],
                "question_type": topic_data['questionType'],
                "subject": topic_data['subjectName'],
                "class_grade": topic_data['classGrade'],
                "topic": topic_data['sectionName'],
                "difficulty": topic_data['difficulty'],
                "bloom_level": topic_data['bloomLevel'],
                "instructions": topic_data.get('additionalInstructions', '')
            })
            
            # Parse response
            llm_output = response['text'] if isinstance(response, dict) and 'text' in response else response
            logger.info(f"Raw LLM output: {llm_output}")
            
            # Clean and parse JSON
            try:
                # Remove any markdown code block markers
                if llm_output.startswith('```'):
                    llm_output = llm_output.split('```')[1]
                if llm_output.startswith('json'):
                    llm_output = llm_output[4:]
                llm_output = llm_output.strip()
                
                result = json.loads(llm_output)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON: {e}")
                # Try to extract JSON object
                match = re.search(r'\{[\s\S]*\}', llm_output)
                if match:
                    try:
                        result = json.loads(match.group(0))
                    except json.JSONDecodeError:
                        raise ValueError("Invalid JSON format in response")
                else:
                    raise ValueError("No valid JSON found in response")
            
            # Validate response
            if not isinstance(result, dict) or 'questions' not in result:
                raise ValueError("Invalid response format: missing 'questions' key")
            
            if not isinstance(result['questions'], list):
                raise ValueError("'questions' must be a list")
            
            # Validate each question
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
            
        except Exception as e:
            logger.error(f"Error generating questions: {e}")
            raise

# Initialize components
document_processor = DocumentProcessor()
question_generator = QuestionGenerator()

#I supressed question evaluation process for now.