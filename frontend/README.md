# Manual PDF Redaction Tool - Frontend

This directory contains the frontend components for the manual PDF redaction tool.

## Installation

The frontend requires the following dependencies:

```bash
npm install pdfjs-dist
# or
yarn add pdfjs-dist
```

## Components

### `components/RedactionTool.jsx`

Main component for manual PDF redaction. Features:
- PDF rendering using pdf.js
- Canvas overlay for drawing redaction boxes
- Click and drag to create redaction boxes
- Delete selected boxes
- Submit redactions to backend API

### `pages/redact.js`

Page component that:
- Loads PDF from query params or file upload
- Displays the RedactionTool component
- Handles redaction completion and redirects

## Usage

1. Install dependencies:
   ```bash
   npm install pdfjs-dist
   ```

2. Import and use the component:
   ```jsx
   import RedactionTool from '@/components/RedactionTool';
   
   function MyPage() {
     const [pdfFile, setPdfFile] = useState(null);
     
     return (
       <RedactionTool 
         pdfFile={pdfFile} 
         onRedactionComplete={(result) => {
           console.log('Redacted PDF URL:', result.document_url);
         }}
       />
     );
   }
   ```

3. Navigate to redaction page:
   ```jsx
   router.push('/redact?id=temp-file-id');
   // or
   router.push('/redact?tempId=temp-file-id');
   ```

## API Integration

The component calls the backend endpoint:
- `POST /api/documents/redact-manual`
- Sends FormData with:
  - `file`: PDF file
  - `redaction_boxes`: JSON array of boxes

## Environment Variables

Set in your `.env.local`:
```
NEXT_PUBLIC_API_URL=http://localhost:8000
```

## Notes

- PDF coordinates are converted from canvas (top-left) to PDF (bottom-left) in the backend
- Redaction boxes are stored in React state and drawn on a canvas overlay
- The component uses pdf.js for PDF rendering

