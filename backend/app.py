from flask import Flask, request, jsonify
from flask_cors import CORS
import cv2
import numpy as np
import base64
import io
from PIL import Image
import face_recognition
import logging
import traceback
from datetime import datetime
import os

app = Flask(__name__)
CORS(app)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class FaceVerificationSystem:
    def __init__(self):
        self.confidence_threshold = 0.6
        self.tolerance = 0.6  # Lower = more strict
        
    def base64_to_image(self, base64_string):
        """Convert base64 string to PIL Image"""
        try:
            # Remove data URL prefix if present
            if ',' in base64_string:
                base64_string = base64_string.split(',')[1]
            
            # Decode base64
            image_data = base64.b64decode(base64_string)
            image = Image.open(io.BytesIO(image_data))
            
            # Convert to RGB if necessary
            if image.mode != 'RGB':
                image = image.convert('RGB')
                
            return np.array(image)
        except Exception as e:
            logger.error(f"Error converting base64 to image: {str(e)}")
            raise Exception(f"Invalid image format: {str(e)}")
    
    def detect_and_encode_face(self, image_array):
        """Detect face and generate encoding"""
        try:
            # Find face locations
            face_locations = face_recognition.face_locations(image_array)
            
            if not face_locations:
                return None, "No face detected in the image"
            
            if len(face_locations) > 1:
                logger.warning("Multiple faces detected, using the first one")
            
            # Generate face encoding
            face_encodings = face_recognition.face_encodings(image_array, face_locations)
            
            if not face_encodings:
                return None, "Could not generate face encoding"
            
            return face_encodings[0], None
            
        except Exception as e:
            logger.error(f"Error in face detection: {str(e)}")
            return None, f"Face detection error: {str(e)}"
    
    def compare_faces(self, encoding1, encoding2):
        """Compare two face encodings"""
        try:
            # Calculate face distance
            face_distance = face_recognition.face_distance([encoding1], encoding2)[0]
            
            # Convert distance to confidence (0-1)
            confidence = max(0, 1 - face_distance)
            
            # Determine if faces match
            is_match = face_distance < self.tolerance
            
            return {
                'match': is_match,
                'confidence': confidence,
                'distance': face_distance
            }
            
        except Exception as e:
            logger.error(f"Error comparing faces: {str(e)}")
            raise Exception(f"Face comparison error: {str(e)}")
    
    def verify_identity(self, profile_image_b64, id_image_b64):
        """Main verification function"""
        try:
            # Convert base64 images to arrays
            profile_image = self.base64_to_image(profile_image_b64)
            id_image = self.base64_to_image(id_image_b64)
            
            # Detect and encode faces
            profile_encoding, profile_error = self.detect_and_encode_face(profile_image)
            if profile_error:
                return {
                    'success': False,
                    'error': f"Profile image: {profile_error}",
                    'match': False,
                    'confidence': 0.0
                }
            
            id_encoding, id_error = self.detect_and_encode_face(id_image)
            if id_error:
                return {
                    'success': False,
                    'error': f"ID image: {id_error}",
                    'match': False,
                    'confidence': 0.0
                }
            
            # Compare faces
            comparison_result = self.compare_faces(profile_encoding, id_encoding)
            
            return {
                'success': True,
                'match': comparison_result['match'],
                'confidence': comparison_result['confidence'],
                'distance': comparison_result['distance'],
                'timestamp': datetime.now().isoformat(),
                'threshold_used': self.tolerance
            }
            
        except Exception as e:
            logger.error(f"Verification error: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'match': False,
                'confidence': 0.0
            }

# Initialize face verification system
face_verifier = FaceVerificationSystem()

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'service': 'Face Verification API'
    })

@app.route('/verify', methods=['POST'])
def verify_identity():
    """Main verification endpoint"""
    try:
        # Get request data
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'error': 'No JSON data provided'
            }), 400
        
        # Validate required fields
        profile_image = data.get('profile_image')
        id_image = data.get('id_image')
        
        if not profile_image or not id_image:
            return jsonify({
                'success': False,
                'error': 'Both profile_image and id_image are required'
            }), 400
        
        # Perform verification
        result = face_verifier.verify_identity(profile_image, id_image)
        
        # Return result
        status_code = 200 if result['success'] else 400
        return jsonify(result), status_code
        
    except Exception as e:
        logger.error(f"API error: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({
            'success': False,
            'error': f'Internal server error: {str(e)}',
            'match': False,
            'confidence': 0.0
        }), 500

@app.route('/config', methods=['GET'])
def get_config():
    """Get current configuration"""
    return jsonify({
        'confidence_threshold': face_verifier.confidence_threshold,
        'tolerance': face_verifier.tolerance,
        'supported_formats': ['jpg', 'jpeg', 'png', 'bmp'],
        'max_image_size': '10MB'
    })

@app.route('/config', methods=['POST'])
def update_config():
    """Update configuration"""
    try:
        data = request.get_json()
        
        if 'tolerance' in data:
            tolerance = float(data['tolerance'])
            if 0.0 <= tolerance <= 1.0:
                face_verifier.tolerance = tolerance
            else:
                return jsonify({'error': 'Tolerance must be between 0.0 and 1.0'}), 400
        
        if 'confidence_threshold' in data:
            threshold = float(data['confidence_threshold'])
            if 0.0 <= threshold <= 1.0:
                face_verifier.confidence_threshold = threshold
            else:
                return jsonify({'error': 'Confidence threshold must be between 0.0 and 1.0'}), 400
        
        return jsonify({
            'success': True,
            'message': 'Configuration updated successfully',
            'tolerance': face_verifier.tolerance,
            'confidence_threshold': face_verifier.confidence_threshold
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.errorhandler(413)
def request_entity_too_large(error):
    """Handle file too large error"""
    return jsonify({
        'success': False,
        'error': 'File too large. Maximum size is 10MB.'
    }), 413

@app.errorhandler(404)
def not_found(error):
    """Handle not found error"""
    return jsonify({
        'success': False,
        'error': 'Endpoint not found'
    }), 404

@app.errorhandler(500)
def internal_error(error):
    """Handle internal server error"""
    logger.error(f"Internal server error: {str(error)}")
    return jsonify({
        'success': False,
        'error': 'Internal server error'
    }), 500

if __name__ == '__main__':
    # Create upload directory if it doesn't exist
    os.makedirs('uploads', exist_ok=True)
    
    # Set maximum file size (10MB)
    app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024
    
    # Start the server
    print("🚀 Face Verification API Server Starting...")
    print("📍 Health check: http://localhost:5100/health")
    print("🔍 Verify endpoint: http://localhost:5100/verify")
    print("⚙️  Config endpoint: http://localhost:5100/config")
    
    app.run(debug=True, host='0.0.0.0', port=5100)
