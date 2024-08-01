import json
import os
import sys
import threading
import time
from time import sleep

import ultimateAlprSdk
from PIL import Image
from flask import Flask, request, jsonify, render_template

counter = 0
bundle_dir = getattr(sys, '_MEIPASS', os.path.abspath(os.path.dirname(__file__)))
boot_time = time.time()

"""
Hi there!

This script is a REST API server that uses the ultimateALPR SDK to process images and return the license plate
information. The server is created using Flask and the ultimateALPR SDK is used to process the images.

See the README.md file for more information on how to run this script.
"""

# Defines the default JSON configuration. More information at
# https://www.doubango.org/SDKs/anpr/docs/Configuration_options.html
JSON_CONFIG = {
    "assets_folder": os.path.join(bundle_dir, "assets"),  # don't change this

    "charset": "latin",
    "car_noplate_detect_enabled": False,
    "ienv_enabled": False,
    "openvino_enabled": True,
    "openvino_device": "CPU",
    "npu_enabled": False,
    "klass_lpci_enabled": False,
    "klass_vcr_enabled": False,
    "klass_vmmr_enabled": False,
    "klass_vbsr_enabled": False,
    "license_token_file": "",
    "license_token_data": "",

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

    "pyramidal_search_enabled": False,
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

config = json.dumps(JSON_CONFIG)


def start_backend_loop():
    global counter, boot_time

    while True:
        load_engine()

        # loop for about an hour or 3000 requests then reload the engine (fix for trial license)
        while counter < 3000 and time.time() - boot_time < 60 * 60:
            # every 120 sec
            if int(time.time()) % 120 == 0:
                if not is_engine_loaded():
                    unload_engine()  # just in case
                    load_engine()

            time.sleep(1)

        unload_engine()

        # Reset counter and boot_time to restart the loop
        counter = 0
        boot_time = time.time()


def is_engine_loaded():
    # hacky way to check if the engine is loaded cause the SDK doesn't provide a method for it
    return ultimateAlprSdk.UltAlprSdkEngine_requestRuntimeLicenseKey().isOK()


def load_engine():
    result = ultimateAlprSdk.UltAlprSdkEngine_init(config)
    if not result.isOK():
        raise RuntimeError("Init failed: %s" % result.phrase())


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

    # TODO: add check for if engine still loaded
    result = ultimateAlprSdk.UltAlprSdkEngine_process(
        image_type,
        image.tobytes(),
        width,
        height,
        0,  # stride
        1  # exifOrientation
    )
    if not result.isOK():
        raise RuntimeError("Process failed: %s" % result.phrase())
    else:
        return result.json()


def create_rest_server_flask():
    app = Flask(__name__, template_folder=os.path.join(bundle_dir, 'templates'))

    @app.route('/v1/image/alpr', methods=['POST'])
    def alpr():
        """
        This function is called when a POST request is made to the /v1/image/alpr endpoint.
        The function receives an image and processes it using the ultimateALPR SDK.

        Parameters:
            - upload: The image to be processed
            - grid_size: The number of cells to split the image into (e.g. 4)
            - wanted_cells: The cells to process in the grid separated by commas (e.g. 1,2,3,4) (max: grid_size²)
        """
        interference = time.time()

        if 'upload' not in request.files:
            return jsonify({'error': 'No image found'})
        if 'grid_size' in request.form and request.form['grid_size'].isdigit():
            grid_size = int(request.form['grid_size'])
        else:
            grid_size = None
        if 'wanted_cells' in request.form and request.form['wanted_cells']:
            wanted_cells = request.form['wanted_cells'].split(',')
            wanted_cells = [int(cell) for cell in wanted_cells]
        else:
            wanted_cells = None

        image = request.files['upload']
        if image.filename == '':
            return jsonify({'error': 'No selected file'})

        image = Image.open(image)
        result = process_image(image)
        result = convert_to_cpai_compatible(result)

        if not result['predictions']:
            print("No plate found in the image, attempting to split the image")

            predictions_found = find_best_plate_with_split(image, grid_size, wanted_cells)

            if predictions_found:
                result['predictions'].append(max(predictions_found, key=lambda x: x['confidence']))

        result['processMs'] = round((time.time() - interference) * 1000, 2)
        result['inferenceMs'] = result['processMs']
        return jsonify(result)

    @app.route('/')
    def index():
        return render_template('index.html')

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


def find_best_plate_with_split(image: Image, grid_size: int = None, wanted_cells: str = None):
    if grid_size is None:
        grid_size = 3
    if wanted_cells is None:
        wanted_cells = list(range(1, grid_size * grid_size + 1))

    predictions_found = []

    width, height = image.size
    cell_width = width // grid_size
    cell_height = height // grid_size

    for cell_index in range(1, grid_size * grid_size + 1):
        row = (cell_index - 1) // grid_size
        col = (cell_index - 1) % grid_size
        left = col * cell_width
        upper = row * cell_height
        right = left + cell_width
        lower = upper + cell_height

        if cell_index in wanted_cells:
            cell_image = image.crop((left, upper, right, lower))
            result_cell = json.loads(process_image(cell_image))

            if 'plates' in result_cell:
                for plate in result_cell['plates']:
                    warpedBox = plate['warpedBox']
                    x_coords = warpedBox[0::2]
                    y_coords = warpedBox[1::2]
                    x_min = min(x_coords) + left
                    x_max = max(x_coords) + left
                    y_min = min(y_coords) + upper
                    y_max = max(y_coords) + upper

                    predictions_found.append({
                        'confidence': plate['confidences'][0] / 100,
                        'label': "Plate: " + plate['text'],
                        'plate': plate['text'],
                        'x_min': x_min,
                        'x_max': x_max,
                        'y_min': y_min,
                        'y_max': y_max
                    })

    return predictions_found


if __name__ == '__main__':
    engine_thread = threading.Thread(target=start_backend_loop, daemon=True)
    engine_thread.start()

    app = create_rest_server_flask()
    app.run(host='0.0.0.0', port=5000)

    unload_engine()
