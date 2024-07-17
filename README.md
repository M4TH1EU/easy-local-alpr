# Easy local ALPR (Automatic License Plate Recognition)

This script is a REST API server that uses [ultimateALPR-SDK](https://github.com/DoubangoTelecom/ultimateALPR-SDK)  to process images and return the license plate
information. The server is created using Flask and the ultimateALPR SDK is used to process the images.

This script is intended to be used as a faster local alternative to the large and resource heavy [CodeProject AI](https://www.codeproject.com/AI/docs) software.
> [!IMPORTANT]
> The ultimateALPR SDK is a lightweight and much faster alternative (on CPU and GPU) to the CodeProject AI software but it has **a few limitations** with it's free version:
> - The last character of the license plate is masked with an asterisk
> - The SDK supposedly has a limit of requests per program execution *(never encountered yet)* **but I have implemented a workaround for this by restarting the SDK after 3000 requests just in case.**


## Usage
The server listens on port 5000 and has one endpoint: /v1/image/alpr. The endpoint accepts POST requests with an
image file in the 'upload' field. The image is processed using the ultimateALPR SDK and the license plate
information is returned in JSON format. The reponse follows the CodeProject AI ALPR API format. So it can be used
as a drop-in replacement for the [CodeProject AI ALPR API](https://www.codeproject.com/AI/docs/api/api_reference.html#license-plate-reader).

> POST: http://localhost:32168/v1/vision/alpr

**Parameters**
- upload: (File) The image file to process. (see [Pillow.Image.open()](https://pillow.readthedocs.io/en/stable/reference/Image.html#PIL.Image.open) for supported formats)

**Response**
```json
{
  "success": (Boolean) // True if successful.
  "message": (String) // A summary of the inference operation.
  "error": (String) // (Optional) An description of the error if success was false.
  "predictions": (Object[]) // An array of objects with the x_max, x_min, max, y_min bounds of the plate, label, the plate chars and confidence.
  "processMs": (Integer) // The time (ms) to process the image (includes inference and image manipulation operations).
}
```


## Included models in built executable
When using the built executable, only the **latin** charset models are bundled by default. If you want to use a different 
charset, you need to set the charset in the JSON_CONFIG variable and rebuild the executable with the according
models found [here](https://github.com/DoubangoTelecom/ultimateALPR-SDK/tree/master/assets)
To build the executable, you can use the ``build_alpr_api.sh`` script, which will create an executable named ``alpr_api`` in
the ``dist`` folder.

## Setup development environment

### Install ultimateALPR SDK
#### Use already built wheel
I have already built the ultimateALPR SDK for x86_64 and ARM64 and included the python3.10 wheel in the wheel folder.
You can install the wheel using : ``pip install wheel/*.whl``
#### Manually build the wheel
If you want to build the wheel yourself, you can use the ``build_and_setup_ultimatealvr.sh`` script. It will create a new
directory ``tmp`` and build the wheel in there. It also includes the assets and libs folders needed when developing.

### Copy necessary files/folders
Then you need to copy the ``assets`` and ``libs`` folders to the same directory as the script.

If you built the wheel in the previous step, you can copy the ``assets`` and ``libs`` folders from the ``tmp`` directory.
If you used the already built wheel, you can find the 'assets' and 'libs' folders on the [GitHub repository](https://github.com/DoubangoTelecom/ultimateALPR-SDK/tree/master/assets)

The structure should look like this:
```bash
.
├── alpr_api.py
├── assets
│   ├── fonts
│   └── models
├── libs
│   ├── libxxxxxx.so
│   ├── ...
│   └── libxxxxxx.so
└── ...
```

### Important notes
When building or developing the script, make sure to set the ``LD_LIBRARY_PATH`` environment variable to the libs folder
*(limitation of the ultimateALPR SDK)*.
```bash
export LD_LIBRARY_PATH=libs:$LD_LIBRARY_PATH
```
