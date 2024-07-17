import json
import os
import sys
import threading
from time import sleep

import ultimateAlprSdk
from PIL import Image
from flask import Flask, request, jsonify

counter = 0

"""
Hi there!

This script is a REST API server that uses the ultimateALPR SDK to process images and return the license plate
information. The server is created using Flask and the ultimateALPR SDK is used to process the images.

See the README.md file for more information on how to run this script.
"""

# Defines the default JSON configuration. More information at https://www.doubango.org/SDKs/anpr/docs/Configuration_options.html
JSON_CONFIG = {
    "debug_level": "info",
    "debug_write_input_image_enabled": False,
    "debug_internal_data_path": ".",

    "num_threads": -1,
    "gpgpu_enabled": True,
    "max_latency": -1,

    "klass_vcr_gamma": 1.5,

    "detect_roi": [0, 0, 0, 0],
    "detect_minscore": 0.35,

    "car_noplate_detect_min_score": 0.8,

    "pyramidal_search_enabled": True,
    "pyramidal_search_sensitivity": 0.38,  # default 0.28
    "pyramidal_search_minscore": 0.8,
    "pyramidal_search_min_image_size_inpixels": 800,

    "recogn_rectify_enabled": True,  # heavy on cpu
    "recogn_minscore": 0.4,
    "recogn_score_type": "min"
}

IMAGE_TYPES_MAPPING = {
    'RGB': ultimateAlprSdk.ULTALPR_SDK_IMAGE_TYPE_RGB24,
    'RGBA': ultimateAlprSdk.ULTALPR_SDK_IMAGE_TYPE_RGBA32,
    'L': ultimateAlprSdk.ULTALPR_SDK_IMAGE_TYPE_Y
}


def load_engine():
    bundle_dir = getattr(sys, '_MEIPASS', os.path.abspath(os.path.dirname(__file__)))

    JSON_CONFIG["assets_folder"] = os.path.join(bundle_dir, "assets")
    JSON_CONFIG["charset"] = "latin"
    JSON_CONFIG["car_noplate_detect_enabled"] = False  # Whether to detect and return cars with no plate
    JSON_CONFIG[
        "ienv_enabled"] = False  # Whether to enable Image Enhancement for Night-Vision (IENV). More info about IENV at https://www.doubango.org/SDKs/anpr/docs/Features.html#image-enhancement-for-night-vision-ienv. Default: true for x86-64 and false for ARM.
    JSON_CONFIG[
        "openvino_enabled"] = False  # Whether to enable OpenVINO. Tensorflow will be used when OpenVINO is disabled
    JSON_CONFIG[
        "openvino_device"] = "GPU"  # Defines the OpenVINO device to use (CPU, GPU, FPGA...). More info at https://www.doubango.org/SDKs/anpr/docs/Configuration_options.html#openvino-device
    JSON_CONFIG["npu_enabled"] = False  # Whether to enable NPU (Neural Processing Unit) acceleration
    JSON_CONFIG[
        "klass_lpci_enabled"] = False  # Whether to enable License Plate Country Identification (LPCI). More info at https://www.doubango.org/SDKs/anpr/docs/Features.html#license-plate-country-identification-lpci
    JSON_CONFIG[
        "klass_vcr_enabled"] = False  # Whether to enable Vehicle Color Recognition (VCR). More info at https://www.doubango.org/SDKs/anpr/docs/Features.html#vehicle-color-recognition-vcr
    JSON_CONFIG[
        "klass_vmmr_enabled"] = False  # Whether to enable Vehicle Make Model Recognition (VMMR). More info at https://www.doubango.org/SDKs/anpr/docs/Features.html#vehicle-make-model-recognition-vmmr
    JSON_CONFIG[
        "klass_vbsr_enabled"] = False  # Whether to enable Vehicle Body Style Recognition (VBSR). More info at https://www.doubango.org/SDKs/anpr/docs/Features.html#vehicle-body-style-recognition-vbsr
    JSON_CONFIG["license_token_file"] = ""  # Path to license token file
    JSON_CONFIG["license_token_data"] = ""  # Base64 license token data

    result = ultimateAlprSdk.UltAlprSdkEngine_init(json.dumps(JSON_CONFIG))
    if not result.isOK():
        raise RuntimeError("Init failed: %s" % result.phrase())

    while counter < 3000:
        sleep(1)

    unload_engine()
    load_engine()


def unload_engine():
    result = ultimateAlprSdk.UltAlprSdkEngine_deInit()
    if not result.isOK():
        raise RuntimeError("DeInit failed: %s" % result.phrase())


def process_image(image: Image) -> str:
    global counter
    counter += 1

    width, height = image.size

    if image.mode in IMAGE_TYPES_MAPPING:
        image_type = IMAGE_TYPES_MAPPING[image.mode]
    else:
        raise ValueError("Invalid mode: %s" % image.mode)

    result = ultimateAlprSdk.UltAlprSdkEngine_process(
        image_type,
        image.tobytes(),  # type(x) == bytes
        width,
        height,
        0,  # stride
        1  # exifOrientation (already rotated in load_image -> use default value: 1)
    )
    if not result.isOK():
        raise RuntimeError("Process failed: %s" % result.phrase())
    else:
        return result.json()


def create_rest_server_flask():
    app = Flask(__name__)

    @app.route('/v1/<string:domain>/<string:module>', methods=['POST'])
    def alpr(domain, module):
        # Only care about the ALPR endpoint
        if domain == 'image' and module == 'alpr':
            if 'upload' not in request.files:
                return jsonify({'error': 'No image found'})

            image = request.files['upload']
            if image.filename == '':
                return jsonify({'error': 'No selected file'})

            image = Image.open(image)
            result = process_image(image)
            result = convert_to_cpai_compatible(result)

            return jsonify(result)
        else:
            return jsonify({'error': 'Endpoint not implemented'}), 404

    return app


def convert_to_cpai_compatible(result):
    result = json.loads(result)

    response = {
        'success': "true",
        'processMs': result['duration'],
        'inferenceMs': result['duration'],
        'predictions': [],
        'message': '',
        'moduleId': 'ALPR',
        'moduleName': 'License Plate Reader',
        'code': 200,
        'command': 'alpr',
        'requestId': 'null',
        'inferenceDevice': 'none',
        'analysisRoundTripMs': 0,
        'processedBy': 'none',
        'timestamp': ''
    }

    if 'plates' in result:
        plates = result['plates']

        for plate in plates:
            warpedBox = plate['warpedBox']
            x_coords = warpedBox[0::2]
            y_coords = warpedBox[1::2]
            x_min = min(x_coords)
            x_max = max(x_coords)
            y_min = min(y_coords)
            y_max = max(y_coords)

            response['predictions'].append({
                'confidence': plate['confidences'][0] / 100,
                'label': "Plate: " + plate['text'],
                'plate': plate['text'],
                'x_min': x_min,
                'x_max': x_max,
                'y_min': y_min,
                'y_max': y_max
            })

    return response


if __name__ == '__main__':
    engine = threading.Thread(target=load_engine, daemon=True)
    engine.start()

    app = create_rest_server_flask()
    app.run(host='0.0.0.0', port=5000)

    unload_engine()
