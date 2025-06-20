import React, { useState } from 'react';
import { useForm, useFieldArray } from 'react-hook-form';
import './styles/QuestionMaker.css';

interface TopicInput {
  sectionName: string;
  questionType: string;
  difficulty: string;
  bloomLevel: string;
  // intelligenceType: string;
  // intelligenceSubType: string;
  numQuestions: string;
  additionalInstructions: string;
  noteId?: string;
}

interface FormInputs {
  email: string;
  subjectName: string;
  classGrade: string;
  language: string;
  topics: TopicInput[];
}

const emptyTopic: TopicInput = {
  sectionName: '',
  questionType: '',
  difficulty: '',
  bloomLevel: '',
  // intelligenceType: '',
  // intelligenceSubType: '',
  numQuestions: '',
  additionalInstructions: '',
  noteId: undefined
};

// const intelligenceSubtypes = {
//   Logical: [
//     "Pattern solving", "Deductive reasoning", "Coding logic", "Data interpretation"
//   ],
//   Linguistic: [
//     "Storytelling", "Persuasive argument", "Vocabulary building", "Creative writing"
//   ],
//   Kinesthetic: [
//     "Gross motor (e.g., sports)", "Fine motor (e.g., drawing)", "Simulations"
//   ],
//   Spatial: [
//     "3D visualization", "Map reading", "Mental rotation", "Blueprint understanding"
//   ],
//   Musical: [
//     "Rhythm patterns", "Composition", "Tone recognition"
//   ],
//   Interpersonal: [
//     "Negotiation skills", "Group collaboration", "Empathy exercises"
//   ],
//   Intrapersonal: [
//     "Self-assessment", "Reflective writing", "Goal setting"
//   ],
//   Naturalistic: [
//     "Classification tasks", "Field observations", "Environmental problem-solving"
//   ]
// };

const App: React.FC = () => {
  const { register, control, handleSubmit } = useForm<FormInputs>({
    defaultValues: {
      email: '',
      subjectName: '',
      classGrade: '',
      language: '',
      topics: [emptyTopic]
    }
  });

  const { fields, append, remove } = useFieldArray({
    control,
    name: "topics"
  });

  const [uploadingFiles, setUploadingFiles] = useState<{ [key: number]: boolean }>({});
  const [analysing, setAnalysing] = useState(false);
  const [analysisSuccess, setAnalysisSuccess] = useState(false);
  const [analysisMessage, setAnalysisMessage] = useState<string | null>(null);

  // Watch intelligence type values for each topic
  // const topics = watch('topics');

  // Comment out intelligence level and number of questions for now
  // const intelligenceLevel = formData.intelligenceLevel;
  // const numQuestions = formData.numQuestions;
  // const handleIntelligenceTypeChange = (index: number, value: string) => {
  //   setValue(`topics.${index}.intelligenceType`, value);
  //   // Reset subtype when type changes
  //   setValue(`topics.${index}.intelligenceSubType`, '');
  // };
  // const handleIntelligenceSubTypeChange = (index: number, value: string) => {
  //   setValue(`topics.${index}.intelligenceSubType`, value);
  // };

  const handleFileUpload = async (file: File, topicIndex: number) => {
    if (!file) return;

    setUploadingFiles(prev => ({ ...prev, [topicIndex]: true }));

    const formData = new FormData();
    formData.append('file', file);

    try {
      const response = await fetch('/api/upload-note', {
        method: 'POST',
        body: formData,
      });

      const result = await response.json();

      if (result.success) {
        // Update the topic's noteId
        const updatedTopics = [...fields];
        updatedTopics[topicIndex].noteId = result.note_id;
        // You might want to show a success message here
      } else {
        alert('Failed to upload file: ' + result.error);
      }
    } catch (error) {
      console.error('Error uploading file:', error);
      alert('Failed to upload file. Please try again.');
    } finally {
      setUploadingFiles(prev => ({ ...prev, [topicIndex]: false }));
    }
  };

  const handleAnalyse = async () => {
    setAnalysing(true);
    setAnalysisSuccess(false);
    setAnalysisMessage(null);
    try {
      const response = await fetch('/api/analyse-note', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ note_id: fields[0].noteId }),
      });
      const result = await response.json();
      if (result.success) {
        setAnalysisSuccess(true);
        setAnalysisMessage('Analysis complete!');
      } else {
        setAnalysisSuccess(false);
        setAnalysisMessage(result.error || 'Analysis failed');
      }
    } catch (e) {
      setAnalysisSuccess(false);
      setAnalysisMessage('Analysis failed');
    }
    setAnalysing(false);
  };

  const onSubmit = async (data: FormInputs) => {
    try {
      const response = await fetch('/api/generate-questions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      });

      if (!response.ok) {
        throw new Error('Failed to generate questions');
      }

      const result = await response.json();

      if (result.success && result.pdf_url) {
        // Open the PDF URL in a new tab
        window.open(result.pdf_url, '_blank');
        // Also redirect to thank you page
        window.location.href = `/thankyou.html?pdf=${encodeURIComponent(result.pdf_url)}`;
      } else {
        throw new Error(result.error || 'Failed to generate questions');
      }
    } catch (error) {
      console.error('Error:', error);
      alert('Failed to generate questions. Please try again.');
    }
  };

  return (
    <div className="question-maker-container">
      <h1>Question Maker</h1>
      <form onSubmit={handleSubmit(onSubmit)}>
        {/* Basic Info Section */}
        <div className="basic-info-section">
          <h2>Basic Information</h2>
          <div className="form-group">
            <label>Email Address *</label>
            <input 
              type="email" 
              {...register("email", { 
                required: true,
                pattern: /^[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}$/i 
              })} 
            />
          </div>
          <div className="form-group">
            <label>Subject Name *</label>
            <input {...register("subjectName", { required: true })} />
          </div>
          <div className="form-group">
            <label>Class/Grade *</label>
            <input {...register("classGrade", { required: true })} />
          </div>
          <div className="form-group">
            <label>Language *</label>
            <select {...register("language", { required: true })}>
              <option value="">Select Language</option>
              <option value="English">English</option>
              <option value="Hindi">Hindi</option>
            </select>
          </div>
          {/* Centralized PDF upload section */}
          <div className="form-group">
            <label>Upload Notes (PDF)</label>
            <div className="file-upload-container" style={{ display: 'flex', alignItems: 'center' }}>
              <input
                type="file"
                accept=".pdf"
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (file) {
                    handleFileUpload(file, 0);
                  }
                }}
                disabled={uploadingFiles[0]}
                style={{ display: 'none' }}
                id="file-upload-central"
              />
              <label htmlFor="file-upload-central" className="file-upload-button">
                {uploadingFiles[0] ? 'Uploading...' : 'Choose File'}
              </label>
              {fields[0].noteId && (
                <span className="file-upload-success">✓ File uploaded successfully</span>
              )}
              <button
                type="button"
                onClick={handleAnalyse}
                disabled={!fields[0].noteId || analysing}
                style={{ marginLeft: 10 }}
              >
                {analysing ? 'Analysing...' : 'Analyse'}
              </button>
              {analysisMessage && (
                <span style={{ color: analysisSuccess ? 'green' : 'red', marginLeft: 8 }}>{analysisMessage}</span>
              )}
            </div>
          </div>
          {/* End Centralized PDF upload section */}
        </div>
        {/* Topics Section */}
        <div className="topics-section">
          <h2>Topics</h2>
          {fields.map((field, index) => (
            <div key={field.id} className="topic-block">
              <h3>Topic {index + 1}</h3>
              <div className="form-group">
                <label>Section/Topic Name *</label>
                <input {...register(`topics.${index}.sectionName`, { required: true })} />
              </div>
              <div className="form-group">
                <label>Question Type *</label>
                <select {...register(`topics.${index}.questionType`, { required: true })}>
                  <option value="">Select Type</option>
                  <option value="MCQ">MCQ</option>
                  <option value="Short">Short Answer</option>
                  <option value="Long">Long Answer</option>
                  <option value="Fill Blanks">Fill in the Blanks</option>
                </select>
              </div>
              <div className="form-group">
                <label>Difficulty *</label>
                <select {...register(`topics.${index}.difficulty`, { required: true })}>
                  <option value="">Select Difficulty</option>
                  <option value="Easy">Easy</option>
                  <option value="Medium">Medium</option>
                  <option value="Hard">Hard</option>
                </select>
              </div>
              <div className="form-group">
                <label>Knowledge Dimension*</label>
                <select {...register(`topics.${index}.bloomLevel`, { required: true })}>
                  <option value="">Select Level</option>
                  <option value="Remember">Remember</option>
                  <option value="Understand">Understand</option>
                  <option value="Apply">Apply</option>
                  <option value="Analyze">Analyze</option>
                  <option value="Evaluate">Evaluate</option>
                  <option value="Create">Create</option>
                </select>
              </div>
              {/* Comment out intelligence level and number of questions for now */}
              {/* <div className="form-group">
                <label>Intelligence Type *</label>
                <select
                  {...register(`topics.${index}.intelligenceType`, { required: true })}
                  onChange={(e) => handleIntelligenceTypeChange(index, e.target.value)}
                >
                  <option value="">Select Intelligence Type</option>
                  {Object.keys(intelligenceSubtypes).map(type => (
                    <option key={type} value={type}>{type}</option>
                  ))}
                </select>
              </div>
              {topics[index]?.intelligenceType && (
                <div className="form-group">
                  <label>Intelligence SubType *</label>
                  <select
                    {...register(`topics.${index}.intelligenceSubType`, { required: true })}
                    onChange={(e) => handleIntelligenceSubTypeChange(index, e.target.value)}
                  >
                    <option value="">Select SubType</option>
                    {(intelligenceSubtypes[topics[index].intelligenceType as keyof typeof intelligenceSubtypes] || []).map((sub: string) => (
                      <option key={sub} value={sub}>{sub}</option>
                    ))}
                  </select>
                </div>
              )} */}
              <div className="form-group">
                <label>Number of Questions *</label>
                <input
                  type="number"
                  {...register(`topics.${index}.numQuestions`, { required: true, min: 1, max: 5 })}
                />
                <div className="input-note">
                  Note: Maximum 3 questions per topic due to AI processing limits. Generation may take 10-15 seconds.
                </div>
              </div>
              <div className="form-group">
                <label>Additional Instructions</label>
                <textarea {...register(`topics.${index}.additionalInstructions`)} />
              </div>
              {index > 0 && (
                <button type="button" onClick={() => remove(index)}>
                  Remove Topic
                </button>
              )}
            </div>
          ))}
          <button type="button" onClick={() => append(emptyTopic)}>
            + Add Topic
          </button>
        </div>
        <div className="submit-section">
          <button type="submit">Submit Paper Request</button>
        </div>
      </form>
    </div>
  );
};

export default App;