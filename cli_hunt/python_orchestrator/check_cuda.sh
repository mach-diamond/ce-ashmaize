#!/bin/bash
# CUDA diagnostic script for Jetson Nano
# Run this to check your CUDA installation status

echo "================================================"
echo "CUDA Installation Diagnostic for Jetson Nano"
echo "================================================"
echo ""

# Check if Jetson
echo "1. Checking Jetson device info..."
if [ -f /etc/nv_tegra_release ]; then
    cat /etc/nv_tegra_release
else
    echo "   Not a Jetson device (or /etc/nv_tegra_release missing)"
fi
echo ""

# Check CUDA directories
echo "2. Checking for CUDA directories..."
for dir in /usr/local/cuda* /usr/local/cuda; do
    if [ -d "$dir" ]; then
        echo "   ✓ Found: $dir"
        if [ -f "$dir/version.txt" ]; then
            echo "     Version: $(cat $dir/version.txt)"
        fi
    fi
done
echo ""

# Check for nvcc
echo "3. Checking for nvcc (CUDA compiler)..."
if command -v nvcc &> /dev/null; then
    echo "   ✓ nvcc found in PATH"
    nvcc --version | head -n 4
else
    echo "   ✗ nvcc not in PATH"
    # Check common locations
    for nvcc_path in /usr/local/cuda/bin/nvcc /usr/local/cuda-10.2/bin/nvcc /usr/local/cuda-10.0/bin/nvcc; do
        if [ -f "$nvcc_path" ]; then
            echo "   ✓ But found at: $nvcc_path"
            echo "   You can add to PATH with:"
            echo "     export PATH=$(dirname $nvcc_path):\$PATH"
            break
        fi
    done
fi
echo ""

# Check CUDA libraries
echo "4. Checking CUDA libraries..."
for lib_dir in /usr/local/cuda/lib64 /usr/local/cuda-10.2/lib64; do
    if [ -d "$lib_dir" ]; then
        echo "   ✓ CUDA libraries found at: $lib_dir"
        echo "     libcudart.so: $(ls $lib_dir/libcudart.so* 2>/dev/null | head -1)"
        break
    fi
done
echo ""

# Check current PATH and LD_LIBRARY_PATH
echo "5. Checking environment variables..."
echo "   PATH contains CUDA: $(echo $PATH | grep -o cuda || echo 'NO')"
echo "   LD_LIBRARY_PATH contains CUDA: $(echo $LD_LIBRARY_PATH | grep -o cuda || echo 'NO')"
echo ""

# Check Python and pip
echo "6. Checking Python environment..."
echo "   Python version: $(python3 --version)"
echo "   pip3 location: $(which pip3)"
echo ""

# Check if PyCUDA is installed
echo "7. Checking PyCUDA installation..."
python3 -c "import pycuda; print('   ✓ PyCUDA version:', pycuda.VERSION)" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "   ✗ PyCUDA not installed"
else
    python3 -c "import pycuda.driver as cuda; import pycuda.autoinit; print('   ✓ PyCUDA can access GPU')" 2>/dev/null
    if [ $? -ne 0 ]; then
        echo "   ⚠ PyCUDA installed but cannot initialize GPU"
    fi
fi
echo ""

# Check GPU
echo "8. Checking GPU status..."
if command -v tegrastats &> /dev/null; then
    echo "   ✓ tegrastats available (for monitoring)"
fi

if [ -f /sys/kernel/debug/tegra_gpu/status ]; then
    echo "   GPU status file exists"
fi

# Try to use nvidia-smi (usually not on Jetson but worth checking)
if command -v nvidia-smi &> /dev/null; then
    echo "   ✓ nvidia-smi available"
    nvidia-smi -L 2>/dev/null | head -1
fi
echo ""

echo "================================================"
echo "Diagnostic complete!"
echo "================================================"
echo ""
echo "Recommendations:"
echo ""

# Provide recommendations based on findings
if ! command -v nvcc &> /dev/null; then
    echo "⚠ CUDA compiler not in PATH"
    echo "  Add to ~/.bashrc:"
    echo "    export PATH=/usr/local/cuda/bin:\$PATH"
    echo "    export LD_LIBRARY_PATH=/usr/local/cuda/lib64:\$LD_LIBRARY_PATH"
    echo ""
fi

if ! python3 -c "import pycuda" 2>/dev/null; then
    echo "⚠ PyCUDA not installed"
    echo "  Install with: pip3 install --user pycuda numpy"
    echo ""
fi

echo "If you need to install JetPack/CUDA:"
echo "  Visit: https://developer.nvidia.com/embedded/jetpack"
echo ""
