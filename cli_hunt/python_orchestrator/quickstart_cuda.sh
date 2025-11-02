#!/bin/bash
# Quick Start Guide for CUDA Acceleration
# Run this on your Jetson Nano

echo "================================================"
echo "CUDA Acceleration Quick Start for Jetson Nano"
echo "================================================"
echo ""

# Step 1: Check CUDA availability
echo "Step 1: Checking CUDA availability..."
if command -v nvcc &> /dev/null; then
    echo "✓ CUDA toolkit found:"
    nvcc --version | head -n 1
else
    echo "✗ CUDA toolkit not found!"
    echo "  Please install JetPack from NVIDIA"
    echo "  Visit: https://developer.nvidia.com/embedded/jetpack"
    exit 1
fi
echo ""

# Step 2: Install Python dependencies
echo "Step 2: Installing Python dependencies..."
if [ -f "requirements-cuda.txt" ]; then
    pip3 install --user -r requirements-cuda.txt
    if [ $? -eq 0 ]; then
        echo "✓ Python dependencies installed"
    else
        echo "✗ Failed to install dependencies"
        exit 1
    fi
else
    echo "✗ requirements-cuda.txt not found"
    echo "  Please run from the python_orchestrator directory"
    exit 1
fi
echo ""

# Step 3: Test PyCUDA
echo "Step 3: Testing PyCUDA installation..."
python3 -c "import pycuda.driver as cuda; import pycuda.autoinit; print('✓ PyCUDA working correctly')" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "✗ PyCUDA test failed"
    echo "  Try: pip3 install --user --upgrade pycuda"
    exit 1
fi
echo ""

# Step 4: Show usage examples
echo "================================================"
echo "Setup complete! You can now use CUDA acceleration"
echo "================================================"
echo ""
echo "Usage examples:"
echo ""
echo "1. Run with CUDA (default 4 workers):"
echo "   python3 main.py run --cuda"
echo ""
echo "2. Run with CUDA and 8 workers:"
echo "   python3 main.py run --cuda --max-solvers 8"
echo ""
echo "3. Monitor GPU usage while running:"
echo "   # In another terminal:"
echo "   tegrastats"
echo "   # or"
echo "   sudo jtop"
echo ""
echo "Performance Tips:"
echo "- Start with --max-solvers 4"
echo "- Monitor thermals with tegrastats"
echo "- Set max performance: sudo nvpmodel -m 0"
echo "- Ensure good cooling for sustained loads"
echo ""
echo "Happy solving! 🚀"
