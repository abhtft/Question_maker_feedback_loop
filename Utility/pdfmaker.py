import io
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
import os

class CreatePDF:
    @staticmethod
    def generate(questions, filename, class_grade='', subject_name='', include_answers=True):
        try:
            # Create PDF in memory
            pdf_buffer = io.BytesIO()
            doc = SimpleDocTemplate(pdf_buffer, pagesize=letter)
            styles = getSampleStyleSheet()
            story = []
            
            # Define custom styles
            title_style = ParagraphStyle(
                'CustomTitle',
                parent=styles['Heading1'],
                fontSize=20,
                spaceAfter=30,
                alignment=1,  # Center alignment
                textColor='#2c3e50'  # Dark blue color
            )
            
            header_style = ParagraphStyle(
                'HeaderStyle',
                parent=styles['Heading2'],
                fontSize=14,
                spaceAfter=20,
                textColor='#34495e'  # Slightly lighter blue
            )
            
            question_style = ParagraphStyle(
                'QuestionStyle',
                parent=styles['Normal'],
                fontSize=12,
                spaceAfter=10,
                textColor='#2c3e50',
                backColor='#f8f9fa',  # Light gray background
                borderPadding=5,
                borderColor='#dee2e6',
                borderWidth=1
            )
            
            option_style = ParagraphStyle(
                'OptionStyle',
                parent=styles['Normal'],
                fontSize=11,
                leftIndent=20,
                spaceAfter=5,
                textColor='#495057'
            )
            
            answer_style = ParagraphStyle(
                'AnswerStyle',
                parent=styles['Normal'],
                fontSize=12,
                spaceAfter=10,
                textColor='#28a745',  # Green color for answers
                backColor='#e8f5e9',  # Light green background
                borderPadding=5,
                borderColor='#c8e6c9',
                borderWidth=1
            )
            
            explanation_style = ParagraphStyle(
                'ExplanationStyle',
                parent=styles['Normal'],
                fontSize=11,
                spaceAfter=20,
                textColor='#6c757d',
                leftIndent=20
            )
            
            # Add title and paper details
            title = "QUESTION PAPER WITH ANSWERS" if include_answers else "QUESTION PAPER"
            story.append(Paragraph(title, title_style))
            
            # Add paper details
            details = [
                f"<b>Class:</b> {class_grade}",
                f"<b>Subject:</b> {subject_name}",
                f"<b>Total Questions:</b> {sum(len(topic.get('questions', [])) for topic in questions)}"
            ]
            
            for detail in details:
                story.append(Paragraph(detail, styles['Normal']))
                story.append(Spacer(1, 5))
            
            story.append(Spacer(1, 20))
            
            # Add questions
            for i, topic in enumerate(questions, 1):
                # Add topic header
                story.append(Paragraph(f"Topic {i}: {topic['topic']}", header_style))
                story.append(Spacer(1, 10))
                
                # Add questions
                for j, q in enumerate(topic['questions'], 1):
                    # Question text
                    story.append(Paragraph(f"Q{j}. {q['question']}", question_style))
                    
                    # Options (if MCQ)
                    if 'options' in q:
                        for opt in q['options']:
                            story.append(Paragraph(f"• {opt}", option_style))
                    
                    # Add answers and explanations only if include_answers is True
                    if include_answers:
                        # Answer
                        story.append(Paragraph(f"<b>Answer:</b> {q['answer']}", answer_style))
                        
                        # Explanation
                        story.append(Paragraph(f"<b>Explanation:</b> {q['explanation']}", explanation_style))
                    
                    # Add spacing between questions
                    story.append(Spacer(1, 15))
            
            # Build the PDF
            doc.build(story)
            pdf_buffer.seek(0)
            return pdf_buffer
            
        except Exception as e:
            print(f"Error generating PDF: {str(e)}")
            raise