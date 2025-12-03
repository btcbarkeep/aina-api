/**
 * Manual PDF Redaction Page
 * 
 * This page loads a PDF file (from query param or uploaded file)
 * and displays the RedactionTool component for manual redaction.
 */

import { useState, useEffect } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import RedactionTool from '../components/RedactionTool';

export default function RedactPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [pdfFile, setPdfFile] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    // Get PDF file from query params or localStorage
    const fileId = searchParams.get('id');
    const tempFileId = searchParams.get('tempId');

    if (fileId || tempFileId) {
      // Load PDF from temporary storage or API
      loadPDFFile(fileId || tempFileId);
    } else {
      // Try to get from localStorage (if uploaded just before)
      const storedFile = localStorage.getItem('pendingRedactionFile');
      if (storedFile) {
        try {
          const fileData = JSON.parse(storedFile);
          // Reconstruct File object from stored data
          fetch(fileData.url)
            .then(res => res.blob())
            .then(blob => {
              const file = new File([blob], fileData.name, { type: 'application/pdf' });
              setPdfFile(file);
              setLoading(false);
            })
            .catch(err => {
              setError('Failed to load PDF file');
              setLoading(false);
            });
        } catch (err) {
          setError('Invalid file data');
          setLoading(false);
        }
      } else {
        setError('No PDF file provided');
        setLoading(false);
      }
    }
  }, [searchParams]);

  const loadPDFFile = async (fileId) => {
    try {
      // Fetch PDF from API or temporary storage
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || '/api';
      const response = await fetch(`${apiUrl}/uploads/temp/${fileId}`, {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token') || ''}`,
        },
      });

      if (!response.ok) {
        throw new Error('Failed to load PDF file');
      }

      const blob = await response.blob();
      const file = new File([blob], `document_${fileId}.pdf`, { type: 'application/pdf' });
      setPdfFile(file);
      setLoading(false);
    } catch (err) {
      setError('Failed to load PDF file: ' + err.message);
      setLoading(false);
    }
  };

  const handleRedactionComplete = (result) => {
    // Store the redacted PDF URL
    localStorage.setItem('redactedPdfUrl', result.document_url);
    localStorage.setItem('redactedPdfS3Key', result.s3_key);

    // Show success message
    alert('Redactions applied successfully! Redirecting to document list...');

    // Redirect to document list or upload completion page
    router.push('/documents?redactionComplete=true');
  };

  const handleFileUpload = (e) => {
    const file = e.target.files[0];
    if (file && file.type === 'application/pdf') {
      setPdfFile(file);
      setError(null);
    } else {
      setError('Please select a PDF file');
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-screen">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-gray-900 mx-auto"></div>
          <p className="mt-4 text-gray-600">Loading PDF...</p>
        </div>
      </div>
    );
  }

  if (error && !pdfFile) {
    return (
      <div className="flex items-center justify-center h-screen">
        <div className="text-center max-w-md">
          <h1 className="text-2xl font-bold text-gray-900 mb-4">PDF Redaction Tool</h1>
          <p className="text-red-600 mb-6">{error}</p>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Upload a PDF file to redact:
            </label>
            <input
              type="file"
              accept="application/pdf"
              onChange={handleFileUpload}
              className="block w-full text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded-md file:border-0 file:text-sm file:font-semibold file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100"
            />
          </div>
        </div>
      </div>
    );
  }

  if (!pdfFile) {
    return (
      <div className="flex items-center justify-center h-screen">
        <div className="text-center max-w-md">
          <h1 className="text-2xl font-bold text-gray-900 mb-4">PDF Redaction Tool</h1>
          <p className="text-gray-600 mb-6">No PDF file provided</p>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Upload a PDF file to redact:
            </label>
            <input
              type="file"
              accept="application/pdf"
              onChange={handleFileUpload}
              className="block w-full text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded-md file:border-0 file:text-sm file:font-semibold file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100"
            />
          </div>
        </div>
      </div>
    );
  }

  return (
    <RedactionTool pdfFile={pdfFile} onRedactionComplete={handleRedactionComplete} />
  );
}

