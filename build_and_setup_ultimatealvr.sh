#!/bin/bash

deactivate 2>/dev/null

# Function to create virtual environment, install the wheel, and copy assets and libs
install_and_setup() {
    echo "Creating virtual environment at the root..."
    python3.10 -m venv "$ROOT_DIR/venv" >/dev/null 2>&1
    if [ $? -ne 0 ]; then
        echo "Failed to create virtual environment."
        exit 1
    fi

    echo "Activating virtual environment..."
    source "$ROOT_DIR/venv/bin/activate"

    echo "Installing the wheel..."
    pip install "$BUILD_DIR"/ultimateAlprSdk-*.whl >/dev/null 2>&1
    if [ $? -ne 0 ]; then
        echo "Failed to install the wheel."
        exit 1
    fi

    echo "Deactivating virtual environment..."
    deactivate

    echo "Copying assets and libs folders to the root directory..."
    cp -r "$BUILD_DIR/assets" "$ROOT_DIR"
    cp -r "$BUILD_DIR/libs" "$ROOT_DIR"

    if [ -f "$ROOT_DIR/requirements.txt" ]; then
        echo "Installing requirements..."
        source "$ROOT_DIR/venv/bin/activate"
        pip install -r "$ROOT_DIR/requirements.txt" >/dev/null 2>&1
        if [ $? -ne 0 ]; then
            echo "Failed to install requirements."
            exit 1
        fi
        deactivate
    fi

    rm -rf "$BUILD_DIR"

    echo "Virtual environment created and wheel installed successfully."
    echo "Assets and libs folders copied to the root directory."

    echo "Setup completed."
}

# Function to prompt user for auto setup choice
prompt_auto_setup() {
    read -r -p "Do you want to automatically create a new virtual environment, install the wheel and copy the assets and libs? (y/n): " choice
    case "$choice" in
        y|Y ) install_and_setup;;
        n|N ) echo "Setup completed.";;
        * ) echo "Invalid choice. Please run the script again and choose y or n.";;
    esac
}

# Variables
ROOT_DIR=$(pwd)
BUILD_DIR="$ROOT_DIR/tmp-build-env"
SDK_ZIP_URL="https://github.com/DoubangoTelecom/ultimateALPR-SDK/archive/febe9921e7dd37e64901d84cad01d51eca6c6a71.zip" # 3.14.1
SDK_ZIP="$BUILD_DIR/temp-sdk.zip"
SDK_DIR="$BUILD_DIR/temp-sdk"
BIN_DIR="$SDK_DIR/binaries/linux/x86_64"

# Create build environment
mkdir -p "$BUILD_DIR"
cd "$BUILD_DIR" || exit

# Clone SDK
echo "Downloading SDK..."
if [ -f "$SDK_ZIP" ]; then
    echo "SDK zip already exists."
    rm -R "$SDK_DIR"
else
    wget "$SDK_ZIP_URL" -O "$SDK_ZIP" >/dev/null 2>&1
fi
if [ $? -ne 0 ]; then
    echo "Failed to download SDK."
    exit 1
fi

echo "Unzipping SDK..."
unzip "$SDK_ZIP" >/dev/null 2>&1
rm "$SDK_ZIP"
mkdir "$SDK_DIR"
mv ultimateALPR-SDK*/* "$SDK_DIR"
rm -r ultimateALPR-SDK*

# Create environment to build ultimatealpr-sdk for Python
echo "Creating virtual environment for building SDK..."
python3.10 -m venv "$BUILD_DIR/venv" >/dev/null 2>&1
if [ $? -ne 0 ]; then
    echo "Failed to create virtual environment."
    exit 1
fi

echo "Activating virtual environment..."
source "$BUILD_DIR/venv/bin/activate"

echo "Installing build dependencies..."
pip install setuptools wheel Cython >/dev/null 2>&1
if [ $? -ne 0 ]; then
    echo "Failed to install build dependencies."
    exit 1
fi

# Move folders to simplify build
mkdir -p "$BIN_DIR/c++"
mv "$SDK_DIR/c++"/* "$BIN_DIR/c++"
mv "$SDK_DIR/python"/* "$BIN_DIR/"

# Edit setup.py to simplify build
echo "Editing setup.py for simplified build..."
cd "$BIN_DIR" || exit
sed -i "s|sources=\[os.path.abspath('../../../python/ultimateALPR-SDK-API-PUBLIC-SWIG_python.cxx')\]|sources=[os.path.abspath('ultimateALPR-SDK-API-PUBLIC-SWIG_python.cxx')]|g" setup.py
sed -i "s|include_dirs=\['../../../c++'\]|include_dirs=['c++']|g" setup.py
sed -i "s|library_dirs=\['.'\]|library_dirs=['libs']|g" setup.py

# Move all .so files into libs folder
mkdir "$BIN_DIR/libs"
mv "$BIN_DIR/"*.so* "$BIN_DIR/libs"

# Download TensorFlow
read -r -p "Do you want TensorFlow for CPU or GPU? (cpu/gpu): " tf_choice
mkdir -p "$BIN_DIR/tensorflow"
if [ "$tf_choice" == "gpu" ]; then
    echo "Downloading TensorFlow GPU..."
    wget https://storage.googleapis.com/tensorflow/libtensorflow/libtensorflow-gpu-linux-x86_64-2.6.0.tar.gz >/dev/null 2>&1 # Use 2.6 for newer GPU support
    if [ $? -ne 0 ]; then
        echo "Failed to download TensorFlow GPU."
        exit 1
    fi
    echo "Extracting TensorFlow GPU..."
    tar -xf libtensorflow-gpu-linux-x86_64-2.6.0.tar.gz -C "$BIN_DIR/tensorflow" >/dev/null 2>&1

    mv "$BIN_DIR/tensorflow/lib/libtensorflow.so.1" "$BIN_DIR/libs/libtensorflow.so.1"
    mv "$BIN_DIR/tensorflow/lib/libtensorflow_framework.so.2.6.0" "$BIN_DIR/libs/libtensorflow_framework.so.2"

else
    echo "Downloading TensorFlow CPU..."
    #wget https://storage.googleapis.com/tensorflow/libtensorflow/libtensorflow-cpu-linux-x86_64-2.6.0.tar.gz >/dev/null 2>&1
    wget https://storage.googleapis.com/tensorflow/libtensorflow/libtensorflow-cpu-linux-x86_64-1.14.0.tar.gz >/dev/null 2>&1 # Use 1.14 as it's smaller in size
    if [ $? -ne 0 ]; then
        echo "Failed to download TensorFlow CPU."
        exit 1
    fi
    echo "Extracting TensorFlow CPU..."
    tar -xf libtensorflow-cpu-linux-x86_64-1.14.0.tar.gz -C "$BIN_DIR/tensorflow" >/dev/null 2>&1

    mv "$BIN_DIR/tensorflow/lib/"* "$BIN_DIR/libs/"
fi

# Build the wheel
echo "Building the wheel..."
python "$BIN_DIR/setup.py" bdist_wheel -v >/dev/null 2>&1
if [ $? -ne 0 ]; then
    echo "Failed to build the wheel."
    exit 1
fi

# Move the built wheel and the libs back to the root directory
mv "$BIN_DIR/dist/"*.whl "$BUILD_DIR"
mv "$BIN_DIR/libs" "$BUILD_DIR"
mv "$BIN_DIR/plugins.xml" "$BUILD_DIR/libs"

# Move the assets to the root directory
mv "$SDK_DIR/assets" "$BUILD_DIR/assets"

# Deactivate and clean up the build virtual environment
echo "Deactivating and cleaning up virtual environment..."
deactivate
cd "$ROOT_DIR" || exit
rm -rf "$BUILD_DIR/venv"
rm -rf "$SDK_DIR"

# Inform the user of the successful build
echo "UltimateALPR SDK built and setup successfully."
echo "You can now create a virtual environment, install the wheel and copy the assets and libs and start developing. Say 'y' to the next prompt to do this automatically (recommended)."
echo "Tip: Look at the assets folder as you might not need all the models depending on your platform/use case."
# Prompt user for auto setup choice
prompt_auto_setup
