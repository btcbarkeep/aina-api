/**
 * Manual PDF Redaction Tool Component
 * 
 * Allows users to draw redaction boxes on a PDF and submit them for processing.
 * Uses pdf.js for PDF rendering and canvas overlay for drawing rectangles.
 */

'use client';

import { useState, useRef, useEffect } from 'react';
import * as pdfjsLib from 'pdfjs-dist';

// Configure pdf.js worker
if (typeof window !== 'undefined') {
  pdfjsLib.GlobalWorkerOptions.workerSrc = `//cdnjs.cloudflare.com/ajax/libs/pdf.js/${pdfjsLib.version}/pdf.worker.min.js`;
}

export default function RedactionTool({ pdfFile, onRedactionComplete }) {
  const [pdfDoc, setPdfDoc] = useState(null);
  const [pages, setPages] = useState([]);
  const [redactions, setRedactions] = useState([]);
  const [currentPage, setCurrentPage] = useState(1);
  const [isDrawing, setIsDrawing] = useState(false);
  const [startPos, setStartPos] = useState(null);
  const [currentBox, setCurrentBox] = useState(null);
  const [selectedBox, setSelectedBox] = useState(null);
  const [isProcessing, setIsProcessing] = useState(false);
  
  const canvasRefs = useRef({});
  const overlayRefs = useRef({});
  const containerRefs = useRef({});

  // Load PDF
  useEffect(() => {
    if (!pdfFile) return;

    const loadPDF = async () => {
      try {
        const arrayBuffer = await pdfFile.arrayBuffer();
        const loadingTask = pdfjsLib.getDocument({ data: arrayBuffer });
        const pdf = await loadingTask.promise;
        setPdfDoc(pdf);

        // Render all pages
        const pagePromises = [];
        for (let i = 1; i <= pdf.numPages; i++) {
          pagePromises.push(renderPage(pdf, i));
        }
        const renderedPages = await Promise.all(pagePromises);
        setPages(renderedPages);
      } catch (error) {
        console.error('Error loading PDF:', error);
        alert('Failed to load PDF: ' + error.message);
      }
    };

    loadPDF();
  }, [pdfFile]);

  // Render a single page
  const renderPage = async (pdf, pageNum) => {
    const page = await pdf.getPage(pageNum);
    const viewport = page.getViewport({ scale: 1.5 });
    
    const canvas = document.createElement('canvas');
    const context = canvas.getContext('2d');
    canvas.height = viewport.height;
    canvas.width = viewport.width;

    await page.render({
      canvasContext: context,
      viewport: viewport,
    }).promise;

    return {
      pageNum,
      canvas,
      viewport,
      width: viewport.width,
      height: viewport.height,
    };
  };

  // Get canvas coordinates from mouse event
  const getCanvasCoordinates = (e, pageNum) => {
    const container = containerRefs.current[pageNum];
    if (!container) return null;

    const rect = container.getBoundingClientRect();
    const scaleX = pages[pageNum - 1]?.width / rect.width;
    const scaleY = pages[pageNum - 1]?.height / rect.height;

    return {
      x: (e.clientX - rect.left) * scaleX,
      y: (e.clientY - rect.top) * scaleY,
    };
  };

  // Handle mouse down - start drawing
  const handleMouseDown = (e, pageNum) => {
    if (e.button !== 0) return; // Only left mouse button
    
    const coords = getCanvasCoordinates(e, pageNum);
    if (!coords) return;

    setIsDrawing(true);
    setStartPos(coords);
    setCurrentBox({
      page: pageNum,
      x: coords.x,
      y: coords.y,
      width: 0,
      height: 0,
    });
    setSelectedBox(null);
  };

  // Handle mouse move - update current box
  const handleMouseMove = (e, pageNum) => {
    if (!isDrawing || !startPos) return;

    const coords = getCanvasCoordinates(e, pageNum);
    if (!coords) return;

    const width = coords.x - startPos.x;
    const height = coords.y - startPos.y;

    setCurrentBox({
      page: pageNum,
      x: width < 0 ? coords.x : startPos.x,
      y: height < 0 ? coords.y : startPos.y,
      width: Math.abs(width),
      height: Math.abs(height),
    });
  };

  // Handle mouse up - finish drawing
  const handleMouseUp = (e, pageNum) => {
    if (!isDrawing || !currentBox) return;

    // Only add box if it has minimum size
    if (currentBox.width > 10 && currentBox.height > 10) {
      setRedactions([...redactions, { ...currentBox, id: Date.now() }]);
    }

    setIsDrawing(false);
    setStartPos(null);
    setCurrentBox(null);
  };

  // Delete selected redaction box
  const deleteBox = (boxId) => {
    setRedactions(redactions.filter(box => box.id !== boxId));
    setSelectedBox(null);
  };

  // Draw redaction boxes on overlay canvas
  const drawOverlay = (pageNum) => {
    const overlay = overlayRefs.current[pageNum];
    if (!overlay) return;

    const ctx = overlay.getContext('2d');
    const page = pages[pageNum - 1];
    if (!page) return;

    // Set canvas size
    overlay.width = page.width;
    overlay.height = page.height;

    // Clear canvas
    ctx.clearRect(0, 0, overlay.width, overlay.height);

    // Draw all redaction boxes for this page
    const pageRedactions = redactions.filter(r => r.page === pageNum);
    pageRedactions.forEach(box => {
      ctx.fillStyle = 'rgba(0, 0, 0, 0.5)';
      ctx.fillRect(box.x, box.y, box.width, box.height);
      
      // Draw border
      ctx.strokeStyle = selectedBox === box.id ? '#ff0000' : '#000000';
      ctx.lineWidth = 2;
      ctx.strokeRect(box.x, box.y, box.width, box.height);
    });

    // Draw current box being drawn
    if (currentBox && currentBox.page === pageNum) {
      ctx.fillStyle = 'rgba(0, 0, 0, 0.3)';
      ctx.fillRect(currentBox.x, currentBox.y, currentBox.width, currentBox.height);
      ctx.strokeStyle = '#000000';
      ctx.lineWidth = 2;
      ctx.strokeRect(currentBox.x, currentBox.y, currentBox.width, currentBox.height);
    }
  };

  // Redraw overlays when redactions change
  useEffect(() => {
    pages.forEach(page => {
      drawOverlay(page.pageNum);
    });
  }, [redactions, currentBox, selectedBox, pages]);

  // Apply redactions - send to backend
  const handleApplyRedactions = async () => {
    if (redactions.length === 0) {
      alert('Please add at least one redaction box before applying.');
      return;
    }

    setIsProcessing(true);

    try {
      // Prepare redaction boxes (remove id, keep only coordinates)
      const boxes = redactions.map(({ id, ...box }) => ({
        page: box.page,
        x: box.x,
        y: box.y,
        width: box.width,
        height: box.height,
      }));

      // Create form data
      const formData = new FormData();
      formData.append('file', pdfFile);
      formData.append('redaction_boxes', JSON.stringify(boxes));

      // Get API base URL from environment or use relative path
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || '/api';
      const response = await fetch(`${apiUrl}/documents/redact-manual`, {
        method: 'POST',
        headers: {
          // Don't set Content-Type - let browser set it with boundary for FormData
          'Authorization': `Bearer ${localStorage.getItem('token') || ''}`,
        },
        body: formData,
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Failed to apply redactions');
      }

      const result = await response.json();
      
      if (onRedactionComplete) {
        onRedactionComplete(result);
      } else {
        alert('Redactions applied successfully! Document URL: ' + result.document_url);
      }
    } catch (error) {
      console.error('Error applying redactions:', error);
      alert('Failed to apply redactions: ' + error.message);
    } finally {
      setIsProcessing(false);
    }
  };

  if (!pdfDoc || pages.length === 0) {
    return (
      <div className="flex items-center justify-center h-screen">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-gray-900 mx-auto"></div>
          <p className="mt-4 text-gray-600">Loading PDF...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-screen bg-gray-100">
      {/* Header */}
      <div className="bg-white shadow-sm border-b px-6 py-4">
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-bold text-gray-900">PDF Redaction Tool</h1>
          <div className="flex items-center gap-4">
            <span className="text-sm text-gray-600">
              Page {currentPage} of {pdfDoc.numPages} | {redactions.length} redaction(s)
            </span>
            <button
              onClick={() => setRedactions([])}
              className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50"
              disabled={redactions.length === 0}
            >
              Clear All
            </button>
            <button
              onClick={handleApplyRedactions}
              disabled={isProcessing || redactions.length === 0}
              className="px-6 py-2 text-sm font-medium text-white bg-blue-600 rounded-md hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed"
            >
              {isProcessing ? 'Processing...' : 'Apply Redactions'}
            </button>
          </div>
        </div>
      </div>

      {/* Page Navigation */}
      <div className="bg-white border-b px-6 py-2 flex items-center justify-center gap-4">
        <button
          onClick={() => setCurrentPage(Math.max(1, currentPage - 1))}
          disabled={currentPage === 1}
          className="px-4 py-1 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          Previous
        </button>
        <span className="text-sm text-gray-600">
          Page {currentPage} of {pdfDoc.numPages}
        </span>
        <button
          onClick={() => setCurrentPage(Math.min(pdfDoc.numPages, currentPage + 1))}
          disabled={currentPage === pdfDoc.numPages}
          className="px-4 py-1 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          Next
        </button>
      </div>

      {/* PDF Viewer */}
      <div className="flex-1 overflow-auto p-6">
        <div className="max-w-4xl mx-auto">
          {pages.map((page) => (
            <div
              key={page.pageNum}
              className={`mb-8 ${page.pageNum === currentPage ? '' : 'hidden'}`}
            >
              <div
                ref={(el) => (containerRefs.current[page.pageNum] = el)}
                className="relative inline-block border border-gray-300 shadow-lg bg-white"
                style={{
                  width: `${page.width}px`,
                  height: `${page.height}px`,
                }}
                onMouseDown={(e) => handleMouseDown(e, page.pageNum)}
                onMouseMove={(e) => handleMouseMove(e, page.pageNum)}
                onMouseUp={(e) => handleMouseUp(e, page.pageNum)}
              >
                {/* PDF Canvas */}
                <canvas
                  ref={(el) => (canvasRefs.current[page.pageNum] = el)}
                  className="absolute top-0 left-0"
                  style={{ pointerEvents: 'none' }}
                />
                {page.canvas && (
                  <img
                    src={page.canvas.toDataURL()}
                    alt={`Page ${page.pageNum}`}
                    className="absolute top-0 left-0"
                    style={{ pointerEvents: 'none' }}
                  />
                )}

                {/* Overlay Canvas for Redactions */}
                <canvas
                  ref={(el) => (overlayRefs.current[page.pageNum] = el)}
                  className="absolute top-0 left-0 cursor-crosshair"
                  style={{ pointerEvents: 'auto' }}
                />

                {/* Redaction Box Controls */}
                {redactions
                  .filter(r => r.page === page.pageNum)
                  .map((box) => (
                    <div
                      key={box.id}
                      className="absolute border-2 border-red-500 bg-transparent hover:bg-red-100 cursor-pointer"
                      style={{
                        left: `${box.x}px`,
                        top: `${box.y}px`,
                        width: `${box.width}px`,
                        height: `${box.height}px`,
                      }}
                      onClick={() => setSelectedBox(box.id)}
                    >
                      {selectedBox === box.id && (
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            deleteBox(box.id);
                          }}
                          className="absolute -top-2 -right-2 w-6 h-6 bg-red-500 text-white rounded-full text-xs hover:bg-red-600"
                        >
                          ×
                        </button>
                      )}
                    </div>
                  ))}
              </div>
              <p className="text-center text-sm text-gray-500 mt-2">
                Page {page.pageNum} - Click and drag to draw redaction boxes
              </p>
            </div>
          ))}
        </div>
      </div>

      {/* Instructions */}
      <div className="bg-white border-t px-6 py-4">
        <p className="text-sm text-gray-600">
          <strong>Instructions:</strong> Click and drag on the PDF to draw black redaction boxes. 
          Click on a box to select it, then click the × button to delete. 
          When finished, click "Apply Redactions" to process the PDF.
        </p>
      </div>
    </div>
  );
}

