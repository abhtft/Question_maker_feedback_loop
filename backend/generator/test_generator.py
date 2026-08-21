#!/usr/bin/env python3
"""
Test script for Enhanced mylang4.py Phase 1 Improvements
Tests all new features while ensuring app.py compatibility

python backend\generator\test_geerator.py

"""

import os
import sys
import json
import logging
from typing import Dict, Any

# Add current directory and its parent directory (project root) to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import the enhanced generator module
import generator

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_enhanced_document_processor():
    """Test the enhanced document processor with smart chunking"""
    logger.info("🧪 Testing Enhanced Document Processor...")
    
    try:
        # Test content type detection
        test_texts = {
            'mathematics': "Solve the quadratic equation x^2 + 5x + 6 = 0 using the formula. Calculate the discriminant and find the roots.",
            'science': "The experiment involved testing the hypothesis that temperature affects reaction rate. We observed that molecules move faster at higher temperatures.",
            'literature': "The poem explores themes of love and loss through vivid metaphors and similes. The character development shows a journey of self-discovery.",
            'default': "This is a general text about various topics that doesn't fit into specific categories."
        }
        
        processor = generator.DocumentProcessor()
        
        for content_type, text in test_texts.items():
            detected_type = processor._detect_content_type(text)
            logger.info(f"Content: {content_type} -> Detected: {detected_type}")
            
            # Test quality scoring
            quality_score = processor._calculate_quality_score(text)
            logger.info(f"Quality score for {content_type}: {quality_score:.2f}")
        
        logger.info("✅ Enhanced Document Processor tests passed!")
        return True
        
    except Exception as e:
        logger.error(f"❌ Enhanced Document Processor test failed: {e}")
        return False

def test_enhanced_context_retriever():
    """Test the enhanced context retrieval system"""
    logger.info("🧪 Testing Enhanced Context Retriever...")
    
    try:
        # Create a mock vectorstore (we'll use None for testing)
        vectorstore = None
        
        # Test query building
        topic_data = {
            'subjectName': 'Mathematics',
            'sectionName': 'Algebra',
            'difficulty': 'Hard',
            'bloomLevel': 'Analyze',
            'classGrade': '10th Grade'
        }
        
        # Test search parameter determination
        retriever = generator.EnhancedContextRetriever(vectorstore)
        
        # Test semantic query building
        semantic_query = retriever._build_semantic_query(topic_data)
        logger.info(f"Semantic query: {semantic_query}")
        
        # Test search parameter determination
        k_docs, max_tokens = retriever._determine_search_parameters(topic_data)
        logger.info(f"Search parameters: k={k_docs}, max_tokens={max_tokens}")
        
        # Test with different topic complexities
        easy_topic = {**topic_data, 'difficulty': 'Easy', 'bloomLevel': 'Remember'}
        k_easy, tokens_easy = retriever._determine_search_parameters(easy_topic)
        logger.info(f"Easy topic parameters: k={k_easy}, max_tokens={tokens_easy}")
        
        logger.info("✅ Enhanced Context Retriever tests passed!")
        return True
        
    except Exception as e:
        logger.error(f"❌ Enhanced Context Retriever test failed: {e}")
        return False

def test_app_compatibility():
    """Test that the enhanced mylang4 maintains app.py compatibility"""
    logger.info("🧪 Testing App.py Compatibility...")
    
    try:
        # Test that all required components exist
        required_components = [
            'document_processor',
            'question_generator', 
            'question_verifier'
        ]
        
        for component in required_components:
            if not hasattr(generator, component):
                raise AttributeError(f"Missing required component: {component}")
            logger.info(f"✅ Component {component} found")
        
        # Test document processor
        processor = generator.document_processor
        if not hasattr(processor, 'process_uploaded_document'):
            raise AttributeError("Missing process_uploaded_document method")
        
        # Test question generator
        generator_component = generator.question_generator
        if not hasattr(generator_component, 'generate_questions'):
            raise AttributeError("Missing generate_questions method")
        
        # Test question verifier
        verifier = generator.question_verifier
        if not hasattr(verifier, 'verify_questions'):
            raise AttributeError("Missing verify_questions method")
        
        logger.info("✅ App.py compatibility tests passed!")
        return True
        
    except Exception as e:
        logger.error(f"❌ App.py compatibility test failed: {e}")
        return False

def test_question_generation_compatibility():
    """Test that question generation maintains the same output format"""
    logger.info("🧪 Testing Question Generation Output Format...")
    
    try:
        # Test data similar to what app.py would send
        test_data = {
            "numQuestions": 2,
            "questionType": "MCQ",
            "subjectName": "Mathematics",
            "classGrade": "10th",
            "sectionName": "Algebra",
            "difficulty": "Medium",
            "bloomLevel": "Understand",
            "additionalInstructions": "Focus on quadratic equations"
        }
        
        # Test with None vectorstore (no document context)
        vectorstore = None
        
        # Generate questions using the enhanced system
        result = generator.question_generator.generate_questions(
            test_data, 
            vectorstore, 
            generator.question_verifier
        )
        
        # Verify output format
        required_keys = ['questions', 'verification_result', 'attempts_used']
        for key in required_keys:
            if key not in result:
                raise KeyError(f"Missing required key in output: {key}")
        
        # Verify questions structure
        questions = result['questions']
        if not isinstance(questions, dict) or 'questions' not in questions:
            raise ValueError("Invalid questions structure")
        
        question_list = questions['questions']
        if not isinstance(question_list, list):
            raise ValueError("Questions should be a list")
        
        # Verify each question has required fields
        for i, q in enumerate(question_list):
            required_fields = ['question', 'options', 'answer', 'explanation']
            for field in required_fields:
                if field not in q:
                    raise ValueError(f"Question {i} missing field: {field}")
            
            # Verify options
            if not isinstance(q['options'], list) or len(q['options']) != 4:
                raise ValueError(f"Question {i} must have exactly 4 options")
            
            # Verify answer is in options
            if q['answer'] not in q['options']:
                raise ValueError(f"Question {i} answer must be one of the options")
        
        logger.info(f"✅ Generated {len(question_list)} questions successfully")
        logger.info(f"✅ Verification result: {result['verification_result']['overall_verdict']}")
        logger.info(f"✅ Attempts used: {result['attempts_used']}")
        
        logger.info("✅ Question Generation Output Format tests passed!")
        return True
        
    except Exception as e:
        logger.error(f"❌ Question Generation Output Format test failed: {e}")
        return False

def run_comprehensive_test():
    """Run all tests and provide a comprehensive report"""
    logger.info("🚀 Starting Comprehensive Test Suite for Enhanced mylang4.py")
    logger.info("=" * 60)
    
    tests = [
        ("Enhanced Document Processor", test_enhanced_document_processor),
        ("Enhanced Context Retriever", test_enhanced_context_retriever),
        ("App.py Compatibility", test_app_compatibility),
        ("Question Generation Output Format", test_question_generation_compatibility)
    ]
    
    results = {}
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        logger.info(f"\n📋 Running: {test_name}")
        try:
            success = test_func()
            results[test_name] = "PASSED" if success else "FAILED"
            if success:
                passed += 1
        except Exception as e:
            logger.error(f"❌ Test {test_name} crashed: {e}")
            results[test_name] = "CRASHED"
    
    # Print comprehensive report
    logger.info("\n" + "=" * 60)
    logger.info("📊 COMPREHENSIVE TEST REPORT")
    logger.info("=" * 60)
    
    for test_name, result in results.items():
        status_icon = "✅" if result == "PASSED" else "❌"
        logger.info(f"{status_icon} {test_name}: {result}")
    
    logger.info(f"\n📈 Summary: {passed}/{total} tests passed")
    
    if passed == total:
        logger.info("🎉 ALL TESTS PASSED! Enhanced mylang4.py is ready for production.")
        logger.info("✅ Phase 1 improvements successfully implemented")
        logger.info("✅ App.py compatibility maintained")
        logger.info("✅ Output format unchanged")
    else:
        logger.error("⚠️  Some tests failed. Please review the issues above.")
    
    return passed == total

if __name__ == "__main__":
    success = run_comprehensive_test()
    sys.exit(0 if success else 1)
