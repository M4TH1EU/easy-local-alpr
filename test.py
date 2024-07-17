import threading
import time

from PIL import Image

import alpr_api
from alpr_api import process_image

if __name__ == '__main__':
    threading.Thread(target=alpr_api.load_engine, daemon=True).start()

    try:
        counter = 0
        while True:
            counter += 1
            # make test request with test_image.png
            image = Image.open('test_image.jpg')
            result = process_image(image)
            print(str(counter) + " - " + result)
            time.sleep(1)
    except KeyboardInterrupt:
        alpr_api.unload_engine()
        exit(0)
