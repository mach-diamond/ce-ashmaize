#!/bin/bash
# Setup script for CUDA acceleration on Jetson Nano
# This installs the necessary dependencies for GPU-accelerated solving

echo "Setting up CUDA dependencies for Jetson Nano..."

# Check if running on Jetson
if [ -f /etc/nv_tegra_release ]; then
    echo "✓ Detected Jetson device:"
    cat /etc/nv_tegra_release
else
    echo "Warning: This doesn't appear to be a Jetson device"
    echo "CUDA setup may not work correctly"
fi
echo ""

# Check for CUDA in common Jetson locations
CUDA_PATHS=(
    "/usr/local/cuda/bin/nvcc"
    "/usr/local/cuda-10.2/bin/nvcc"
    "/usr/local/cuda-10.0/bin/nvcc"
)

NVCC_FOUND=""
for cuda_path in "${CUDA_PATHS[@]}"; do
    if [ -f "$cuda_path" ]; then
        NVCC_FOUND="$cuda_path"
        break
    fi
done

if [ -n "$NVCC_FOUND" ]; then
    echo "✓ CUDA toolkit found at: $NVCC_FOUND"
    $NVCC_FOUND --version
    # Add to PATH if not already there
    CUDA_BIN_DIR=$(dirname "$NVCC_FOUND")
    if [[ ":$PATH:" != *":$CUDA_BIN_DIR:"* ]]; then
        export PATH="$CUDA_BIN_DIR:$PATH"
        echo "  Added $CUDA_BIN_DIR to PATH"
    fi
elif command -v nvcc &> /dev/null; then
    echo "✓ CUDA toolkit found in PATH:"
    nvcc --version
    NVCC_FOUND="nvcc"
else
    echo "✗ CUDA toolkit not found!"
    echo ""
    echo "Checking for CUDA installation..."
    if [ -d /usr/local/cuda ]; then
        echo "  CUDA directory exists at /usr/local/cuda"
        echo "  But nvcc not found. Try adding to PATH:"
        echo "    export PATH=/usr/local/cuda/bin:\$PATH"
    else
        echo "  CUDA not installed. Please install JetPack from NVIDIA."
        echo "  Visit: https://developer.nvidia.com/embedded/jetpack"
    fi
    exit 1
fi
echo ""

# Install system dependencies
echo "Installing system dependencies..."
sudo apt-get update
sudo apt-get install -y python3-pip python3-dev build-essential

# Install Python CUDA dependencies
echo ""
echo "Installing PyCUDA..."
pip3 install --user -r requirements-cuda.txt

if [ $? -ne 0 ]; then
    echo ""
    echo "PyCUDA installation failed. Trying alternative method..."
    # On Jetson, sometimes need to specify CUDA path explicitly
    if [ -d /usr/local/cuda ]; then
        export CUDA_ROOT=/usr/local/cuda
        pip3 install --user pycuda
    fi
fi

# Verify installation
echo ""
echo "Verifying PyCUDA installation..."
python3 -c "import pycuda.driver as cuda; import pycuda.autoinit; print('✓ PyCUDA installed successfully!')" 2>/dev/null

if [ $? -eq 0 ]; then
    echo ""
    echo "================================================"
    echo "✓ CUDA setup complete!"
    echo "================================================"
    echo ""
    echo "You can now run: python3 main.py run --cuda"
    echo ""
    echo "Performance tips:"
    echo "  - Start with: python3 main.py run --cuda --max-solvers 4"
    echo "  - Monitor GPU: tegrastats"
    echo "  - Max performance: sudo nvpmodel -m 0"
else
    echo ""
    echo "✗ PyCUDA verification failed"
    echo ""
    echo "Troubleshooting steps:"
    echo "1. Ensure CUDA is in PATH:"
    echo "   export PATH=/usr/local/cuda/bin:\$PATH"
    echo "   export LD_LIBRARY_PATH=/usr/local/cuda/lib64:\$LD_LIBRARY_PATH"
    echo ""
    echo "2. Try manual PyCUDA install:"
    echo "   pip3 install --user pycuda"
    echo ""
    echo "3. Check CUDA installation:"
    echo "   ls -la /usr/local/cuda"
    echo ""
    exit 1
fi
