import base64
import io
import json
import logging
import os
import sys
import threading
import time
import traceback

import ultimateAlprSdk
from PIL import Image, ImageDraw, ImageFont
from flask import Flask, request, jsonify, render_template

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

counter_lock = threading.Lock()
counter = 0
bundle_dir = getattr(sys, '_MEIPASS', os.path.abspath(os.path.dirname(__file__)))
boot_time = time.time()

"""
Hi there!

This script is a REST API server that uses the ultimateALPR SDK to process images and return the license plate
information. The server is created using Flask and the ultimateALPR SDK is used to process the images.

See the README.md file for more information on how to run this script.
"""

# Load configuration
CONFIG_PATH = os.path.join(bundle_dir,
                           'config.json')  # TODO: store config file outside of bundle (to remove need for compilation by users)
if os.path.exists(CONFIG_PATH):
    with open(CONFIG_PATH, 'r') as config_file:
        JSON_CONFIG = json.load(config_file)
else:
    JSON_CONFIG = {
        "assets_folder": os.path.join(bundle_dir, "assets"),
        "charset": "latin",
        "car_noplate_detect_enabled": False,
        "ienv_enabled": True,  # night vision enhancements
        "openvino_enabled": True,
        "openvino_device": "CPU",
        "npu_enabled": False,
        "klass_lpci_enabled": False,  # License Plate Country Identification
        "klass_vcr_enabled": False,  # Vehicle Color Recognition (paid)
        "klass_vmmr_enabled": False,  # Vehicle Make and Model Recognition
        "klass_vbsr_enabled": False,  # Vehicle Body Style Recognition (paid)
        "license_token_file": "",
        "license_token_data": "",

        "debug_level": "fatal",
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
        "pyramidal_search_sensitivity": 0.38,
        "pyramidal_search_minscore": 0.8,
        "pyramidal_search_min_image_size_inpixels": 800,
        "recogn_rectify_enabled": True,
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
    global boot_time, counter

    while True:
        load_engine()

        # loop for about an hour or 3000 requests then reload the engine (fix for trial license)
        while counter < 3000 and time.time() - boot_time < 3600:
            # every 120 sec
            if int(time.time()) % 120 == 0:
                if not is_engine_loaded():
                    unload_engine()
                    load_engine()
            time.sleep(1)

        unload_engine()

        # Reset counter and boot_time to restart the loop
        with counter_lock:
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
    with counter_lock:
        counter += 1

    width, height = image.size
    image_type = IMAGE_TYPES_MAPPING.get(image.mode, None)
    if image_type is None:
        raise ValueError(f"Invalid mode: {image.mode}")

    result = ultimateAlprSdk.UltAlprSdkEngine_process(
        image_type, image.tobytes(), width, height, 0, 1
    )
    if not result.isOK():
        raise RuntimeError(f"Process failed: {result.phrase()}")
    return result.json()


def create_rest_server_flask():
    app = Flask(__name__, template_folder=os.path.join(bundle_dir, 'templates'))

    @app.route('/v1/image/alpr', methods=['POST'])
    def alpr():
        """
        The function receives an image and processes it using the ultimateALPR SDK.

        Parameters:
            - upload: The image to be processed
            - grid_size: The number of cells to split the image into (e.g. 3)
            - wanted_cells: The cells to process in the grid separated by commas (e.g. 1,2,3,4) (max: grid_size²)
            - whole_image_fallback: If set to true, the whole image will be processed if no plates are found in the specified cells. (default: true)
        """
        interference = time.time()
        whole_image_fallback = request.form.get('whole_image_fallback', 'true').lower() == 'true'

        try:
            if 'upload' not in request.files:
                return jsonify({'error': 'No image found'}), 400

            grid_size = int(request.form.get('grid_size', 1))
            wanted_cells = _get_wanted_cells_from_request(request, grid_size)

            image_file = request.files['upload']
            if image_file.filename == '':
                return jsonify({'error': 'No selected file'}), 400

            image = _load_image_from_request(request)

            result = {
                'predictions': [],
                'plates': [],
                'duration': 0
            }

            if grid_size < 2:
                logger.debug("Grid size < 2, processing the whole image")
                response = process_image(image)
                result.update(_parse_result_from_ultimatealpr(response))
            else:
                logger.debug(f"Grid size: {grid_size}, processing specified cells: {wanted_cells}")
                predictions_found = _find_best_plate_with_grid_split(image, grid_size, wanted_cells)
                result['predictions'].extend(predictions_found)

            if not result['predictions']:
                if grid_size >= 2 and whole_image_fallback:
                    logger.debug("No plates found in the specified cells, trying whole image as last resort")
                    response = process_image(image)
                    result.update(_parse_result_from_ultimatealpr(response))

            if result['predictions'] and len(result['predictions']) > 0:
                all_plates = []
                for plate in result['predictions']:
                    all_plates.append(plate.get('plate'))
                    isolated_plate_image = isolate_plate_in_image(image, plate)
                    plate['image'] = f"data:image/png;base64,{image_to_base64(isolated_plate_image, compress=True)}"

                result['plates'] = all_plates

            duration = round((time.time() - interference) * 1000, 2)
            result.update({'duration': duration})
            return jsonify(result)
        except Exception as e:
            logger.error(f"Error processing image: {e}")
            logger.error(traceback.format_exc())
            return jsonify({'error': 'Error processing image'}), 500

    @app.route('/v1/image/alpr_grid_debug', methods=['POST'])
    def alpr_grid_debug():
        """
        The function receives an image and returns it with the grid overlayed on it (for debugging purposes).

        Parameters:
            - upload: The image to be processed
            - grid_size: The number of cells to split the image into (e.g. 3)
            - wanted_cells: The cells to process in the grid separated by commas (e.g. 1,2,3,4) (max: grid_size²)

        Returns:
            - The image with the grid overlayed on it
        """
        try:
            if 'upload' not in request.files:
                return jsonify({'error': 'No image found'}), 400

            grid_size = int(request.form.get('grid_size', 3))
            wanted_cells = _get_wanted_cells_from_request(request, grid_size)

            image_file = request.files['upload']
            if image_file.filename == '':
                return jsonify({'error': 'No selected file'}), 400

            image = _load_image_from_request(request)
            image = draw_grid_and_cell_numbers_on_image(image, grid_size, wanted_cells)

            image_base64 = image_to_base64(image, compress=True)
            return jsonify({"image": f"data:image/png;base64,{image_base64}"})
        except Exception as e:
            logger.error(f"Error processing image: {e}")
            logger.error(traceback.format_exc())
            return jsonify({'error': 'Error processing image'}), 500

    @app.route('/')
    def index():
        return render_template('index.html')

    return app


def _get_wanted_cells_from_request(request, grid_size) -> list:
    """
    Helper function to extract wanted cells from the request.
    If no cells are specified, it returns all cells in the grid.
    """
    wanted_cells = request.form.get('wanted_cells')
    if wanted_cells:
        wanted_cells = [int(cell) for cell in wanted_cells.split(',')]
    else:
        wanted_cells = list(range(1, grid_size * grid_size + 1))

    if not all(1 <= cell <= grid_size * grid_size for cell in wanted_cells):
        raise ValueError("Invalid cell numbers provided.")

    return wanted_cells


def _load_image_from_request(request) -> Image:
    """
    Helper function to load an image from the request.
    It expects the image to be in the 'upload' field of the request.
    """
    if 'upload' not in request.files:
        raise ValueError("No image found in request.")

    image_file = request.files['upload']
    if image_file.filename == '':
        raise ValueError("No selected file.")

    try:
        image = Image.open(image_file)
        return correct_image_orientation(image)
    except Exception as e:
        raise ValueError(f"Error loading image: {e}")


def _parse_result_from_ultimatealpr(result) -> dict:
    result = json.loads(result)
    response = {
        'predictions': [],
    }

    for plate in result.get('plates', []):
        warpedBox = plate['warpedBox']
        x_coords = warpedBox[0::2]
        y_coords = warpedBox[1::2]
        x_min, x_max = min(x_coords), max(x_coords)
        y_min, y_max = min(y_coords), max(y_coords)

        response['predictions'].append({
            'confidence': plate['confidences'][0] / 100,
            'plate': plate['text'],
            'x_min': x_min,
            'x_max': x_max,
            'y_min': y_min,
            'y_max': y_max
        })
    return response


def _find_best_plate_with_grid_split(image: Image, grid_size: int = 3, wanted_cells: list = None,
                                     stop_at_first_match: bool = False) -> list:
    """
    Splits the image into a grid and processes each cell to find the best plate.
    Returns a list of predictions found in the specified cells.
    """

    if grid_size < 2:
        logger.debug("Grid size < 2, skipping split")
        return []

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
            result = process_image(cell_image)
            logger.info(f"Processed image with result (grid): {result}")
            result_cell = json.loads(result)

            for plate in result_cell.get('plates', []):
                warpedBox = plate['warpedBox']
                x_coords = warpedBox[0::2]
                y_coords = warpedBox[1::2]
                x_min = min(x_coords) + left
                x_max = max(x_coords) + left
                y_min = min(y_coords) + upper
                y_max = max(y_coords) + upper

                predictions_found.append({
                    'confidence': plate['confidences'][0] / 100,
                    'plate': plate['text'],
                    'x_min': x_min,
                    'x_max': x_max,
                    'y_min': y_min,
                    'y_max': y_max
                })

                if stop_at_first_match:
                    logger.debug(f"Found plate in cell {cell_index}: {plate['text']}")
                    return predictions_found

    return predictions_found


def draw_grid_and_cell_numbers_on_image(image: Image, grid_size: int = 3, wanted_cells: list = None) -> Image:
    """
    Draws a grid on the image and numbers the cells.
    """

    if grid_size < 1:
        grid_size = 1

    if wanted_cells is None:
        wanted_cells = list(range(1, grid_size * grid_size + 1))

    width, height = image.size
    cell_width = width // grid_size
    cell_height = height // grid_size

    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype(os.path.join(bundle_dir, 'assets', 'fonts', 'GlNummernschildEng-XgWd.ttf'),
                              image.size[0] // 10)

    for cell_index in range(1, grid_size * grid_size + 1):
        row = (cell_index - 1) // grid_size
        col = (cell_index - 1) % grid_size
        left = col * cell_width
        upper = row * cell_height
        right = left + cell_width
        lower = upper + cell_height

        if cell_index in wanted_cells:
            draw.rectangle([left, upper, right, lower], outline="red", width=4)
            draw.text((left + 5, upper + 5), str(cell_index), fill="red", font=font)

    return image


def isolate_plate_in_image(image: Image, plate: dict, offset=10) -> Image:
    """
    Isolates the plate area in the image and returns a cropped and resized image.
    """

    x_min, x_max = plate.get('x_min'), plate.get('x_max')
    y_min, y_max = plate.get('y_min'), plate.get('y_max')

    cropped_image = image.crop((max(0, x_min - offset), max(0, y_min - offset), min(image.size[0], x_max + offset),
                                min(image.size[1], y_max + offset)))
    resized_image = cropped_image.resize((int(cropped_image.size[0] * 3), int(cropped_image.size[1] * 3)),
                                         resample=Image.Resampling.LANCZOS)

    return resized_image


def image_to_base64(img: Image, compress=False) -> str:
    """Convert a Pillow image to a base64-encoded string."""

    buffered = io.BytesIO()
    if compress:
        img = img.resize((img.size[0] // 2, img.size[1] // 2))
        img.save(buffered, format="WEBP", quality=35, lossless=False)
    else:
        img.save(buffered, format="WEBP")

    return base64.b64encode(buffered.getvalue()).decode('utf-8')


from PIL import Image, ExifTags


def correct_image_orientation(img):
    try:
        exif = img._getexif()
        if exif is not None:
            orientation_key = next(
                (k for k, v in ExifTags.TAGS.items() if v == 'Orientation'), None)
            if orientation_key is not None:
                orientation = exif.get(orientation_key)
                if orientation == 3:
                    img = img.rotate(180, expand=True)
                elif orientation == 6:
                    img = img.rotate(270, expand=True)
                elif orientation == 8:
                    img = img.rotate(90, expand=True)
    except Exception as e:
        print("EXIF orientation correction failed:", e)
    return img


if __name__ == '__main__':
    engine_thread = threading.Thread(target=start_backend_loop, daemon=True)
    engine_thread.start()

    app = create_rest_server_flask()
    app.run(host='0.0.0.0', port=5000)

    unload_engine()
