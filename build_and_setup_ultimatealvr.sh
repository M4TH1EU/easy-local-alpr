# clone sdk
mkdir ./tmp
cd tmp
wget https://github.com/DoubangoTelecom/ultimateALPR-SDK/archive/8130c76140fe8edc60fe20f875796121a8d22fed.zip -O temp-sdk.zip
unzip temp-sdk.zip
rm temp-sdk.zip

mkdir temp-sdk
mv ultimateALPR-SDK*/* ./temp-sdk
rm -R ultimateALPR-SDK*

# create env to build ultimatealpr-sdk for python
python3.10 -m venv venv
source venv/bin/activate
pip install setuptools wheel Cython

cd temp-sdk

# move folders to simplify build
mkdir -p binaries/linux/x86_64/c++
cp c++/* binaries/linux/x86_64/c++
cp python/* binaries/linux/x86_64/

# edit setup.py to simplify build
cd binaries/linux/x86_64/
sed -i "s|sources=\[os.path.abspath('../../../python/ultimateALPR-SDK-API-PUBLIC-SWIG_python.cxx')\]|sources=[os.path.abspath('ultimateALPR-SDK-API-PUBLIC-SWIG_python.cxx')]|g" setup.py
sed -i "s|include_dirs=\['../../../c++'\]|include_dirs=['c++']|g" setup.py
sed -i "s|library_dirs=\['.'\]|library_dirs=['libs']|g" setup.py

# move all .so files into libs folder
mkdir libs
mv *.so libs/
mv *.so.* libs/

# build the wheel
python setup.py bdist_wheel -v

# move the built whl and the libs back to root dir
mv dist/* ../../../../

mv libs ../../../../

# move the assets to root dir
cd ../../../
mv assets ../assets

## install the whl
#cd ..
#pip install *.whl
#rm *.whl

cd ../

# remove sdk
rm -R temp-sdk

echo "UltimateALPR SDK built and setup successfully"
echo "You can now install the wheel using 'pip install ultimateAlprSdk-*.whl'"