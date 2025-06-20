import os
import json
from mylang4 import DocumentProcessor, QuestionGenerator, QuestionEvaluator
from dotenv import load_dotenv
import re

# Load environment variables
load_dotenv()

import logging
from datetime import datetime

# Ensure 'logging' directory exists
log_dir = "logging"
os.makedirs(log_dir, exist_ok=True)

# Create log filename with timestamp
log_filename = f"{log_dir}/test_langchain1_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

logging.basicConfig(
    filename=log_filename,
    level=logging.INFO,
    format='%(message)s'
)

def print_step(step_name: str):
    """Print a formatted step header"""
    print("\n" + "="*50)
    print(f"STEP: {step_name}")
    print("="*50)

def save_questions_to_file(questions, filename="generated_questions.json"):
    """Save generated questions to a JSON file"""
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(questions, f, indent=4)
        print(f"\nQuestions have been saved to {filename}")
    except Exception as e:
        print(f"Error saving questions to file: {str(e)}")

def test_pdf_processing():
    print_step("1. PDF Processing")
    processor = DocumentProcessor()
    
    # Test with a sample PDF
    pdf_path = "sample.pdf"
    if not os.path.exists(pdf_path):
        print(f"Error: {pdf_path} not found. Please place a sample PDF in the directory.")
        return False
    
    try:
        print(f"Processing PDF: {pdf_path}")
        print("\nSteps in PDF processing:")
        print("1. Loading PDF using PyPDFLoader")
        print("2. Splitting text into chunks")
        print("3. Creating vector store with FAISS")
        
        vectorstore, texts = processor.process_uploaded_document(pdf_path)
        print(f"\nSuccessfully processed PDF into {len(texts)} chunks")
        print("First chunk preview:")
        if texts:
            print(texts[0].page_content[:200] + "...")
        return vectorstore, texts
    except Exception as e:
        print(f"Error processing PDF: {str(e)}")
        import traceback
        print("Full error traceback:")
        print(traceback.format_exc())
        return False

def test_question_generation(vectorstore=None, texts=None):
    print_step("2. Question Generation")
    generator = QuestionGenerator()
    
    # Sample topic data
    topic_data = {
        "subjectName": "Biology",
        "sectionName": "Life Process",
        "questionType": "Short Answer",
        "classGrade": "10",
        "difficulty": "Hard",
        "bloomLevel": "Understand",
        "numQuestions": 2,
        "additionalInstructions": ""
    }
    
    try:
        if vectorstore is None:
            print("No vectorstore provided, processing PDF again...")
            processor = DocumentProcessor()
            pdf_path = "sample.pdf"
            if not os.path.exists(pdf_path):
                print(f"Error: {pdf_path} not found.")
                return False
            vectorstore, texts = processor.process_uploaded_document(pdf_path)
        
        print("\nSteps in question generation:")
        print("1. Searching for relevant context in vector store")
        print("2. Generating questions using LLM")
        print("3. Formatting questions into JSON structure")
        
        # Generate questions
        questions = generator.generate_questions(topic_data, vectorstore)
        
        print("\n=== Generated Questions ===")
        if 'text' in questions:
            try:
                raw = questions['text']
                # Remove markdown code block markers
                cleaned = re.sub(r"^```json|```$", "", raw, flags=re.MULTILINE).strip()
                parsed_questions = json.loads(cleaned)
                if len(parsed_questions['questions']) != topic_data['numQuestions']:
                    print(f"Warning: Requested {topic_data['numQuestions']} questions, but got {len(parsed_questions['questions'])}")
                for i, q in enumerate(parsed_questions['questions'], 1):
                    print(f"\nQuestion {i}:")
                    print(f"Q: {q['question']}")
                    print("\nOptions:")
                    for opt in q['options']:
                        print(f"- {opt}")
                    print(f"\nAnswer: {q['answer']}")
                    print(f"Explanation: {q['explanation']}")
                    print("-" * 80)
                
                save_questions_to_file(parsed_questions)
            except json.JSONDecodeError:
                print("Error parsing questions JSON")
                print("Raw questions:", questions['text'])
        else:
            print("Questions format not as expected")
            print("Raw questions:", questions)
        
        return True
    except Exception as e:
        print(f"Error generating questions: {str(e)}")
        import traceback
        print("Full error traceback:")
        print(traceback.format_exc())
        return False

def test_question_evaluation(vectorstore=None, texts=None):
    print_step("3. Question Evaluation")
    evaluator = QuestionEvaluator()
    
    try:
        print("\nSteps in question evaluation:")
        print("1. Loading QA evaluator")
        print("2. Evaluating questions against context")
        print("3. Generating evaluation metrics")
        
        # First generate questions if not already done
        if vectorstore is None:
            print("No vectorstore provided, processing PDF again...")
            processor = DocumentProcessor()
            pdf_path = "sample.pdf"
            if not os.path.exists(pdf_path):
                print(f"Error: {pdf_path} not found.")
                return False
            vectorstore, texts = processor.process_uploaded_document(pdf_path)
            
            generator = QuestionGenerator()
            topic_data = {
                "subjectName": "Biology",
                "sectionName": "Life Process",
                "questionType": "MCQ",
                "classGrade": "10",
                "difficulty": "Hard",
                "knowledgeDimension": "Understand",
                "numQuestions": 2,
                "additionalInstructions": ""
            }
            questions = generator.generate_questions(topic_data, vectorstore)
            parsed_questions = json.loads(questions['text'])
        else:
            # Load questions from the saved file
            try:
                with open("generated_questions.json", 'r') as f:
                    parsed_questions = json.load(f)
            except FileNotFoundError:
                print("Error: generated_questions.json not found")
                return False
        
        # Evaluate each question
        print("\nEvaluating generated questions:")
        for i, question in enumerate(parsed_questions['questions'], 1):
            print(f"\nEvaluating Question {i}:")
            print(f"Question: {question['question']}")
            print(f"Answer: {question['answer']}")
            
            # Get relevant context for this question
            relevant_docs = vectorstore.similarity_search(
                question['question'],
                k=2
            )
            context = "\n".join([doc.page_content for doc in relevant_docs])
            
            try:
                evaluation = evaluator.evaluate_question(question, context)
                print("\nEvaluation Result:")
                print(evaluation)
            except Exception as e:
                print(f"Error evaluating question {i}: {str(e)}")
                continue
        
        return True
    except Exception as e:
        print(f"Error in evaluation process: {str(e)}")
        import traceback
        print("Full error traceback:")
        print(traceback.format_exc())
        return False

def main():
    print("\nStarting LangChain Integration Tests...")
    print("This test will demonstrate the following sequence:")
    print("1. PDF Processing: Load and chunk the PDF")
    print("2. Question Generation: Create questions from the content")
    print("3. Question Evaluation: Evaluate question quality")
    
    # Check if OpenAI API key is set
    if not os.getenv("OPENAI_API_KEY"):
        print("Error: OPENAI_API_KEY not found in environment variables")
        return
    
    # Run tests
    pdf_result = test_pdf_processing()
    if pdf_result and isinstance(pdf_result, tuple):
        vectorstore, texts = pdf_result
        question_success = test_question_generation(vectorstore, texts)
        eval_success = test_question_evaluation(vectorstore, texts)
        
        print("\n=== Test Summary ===")
        print(f"PDF Processing: ✓")
        print(f"Question Generation: {'✓' if question_success else '✗'}")
        print(f"Question Evaluation: {'✓' if eval_success else '✗'}")
    else:
        print("\nSkipping remaining tests due to PDF processing failure")

if __name__ == "__main__":
    main() 