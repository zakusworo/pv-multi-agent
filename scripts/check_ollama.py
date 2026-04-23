#!/usr/bin/env python3
"""
Check Ollama setup and download models if needed
"""

import subprocess
import sys
import time


def check_ollama():
    """Check if Ollama is installed and running"""
    try:
        import ollama
        ollama.list()
        print("✓ Ollama is running")
        return True
    except ImportError:
        print("❌ ollama Python package not installed")
        print("   Install with: pip install ollama")
        return False
    except Exception as e:
        print(f"❌ Ollama not accessible: {e}")
        print("   Make sure Ollama server is running: ollama serve")
        return False


def check_model(model: str = "llama3.2"):
    """Check if model is downloaded"""
    try:
        import ollama
        models = ollama.list()
        model_names = [m['model'] for m in models.get('models', [])]
        
        if f"{model}:latest" in model_names or model in model_names:
            print(f"✓ Model '{model}' is available")
            return True
        else:
            print(f"⚠ Model '{model}' not found")
            print(f"   Download with: ollama pull {model}")
            return False
    except:
        return False


def install_model(model: str):
    """Download model via Ollama"""
    print(f"\n📥 Downloading {model}...")
    try:
        result = subprocess.run(
            ['ollama', 'pull', model],
            capture_output=True,
            text=True,
            timeout=600
        )
        if result.returncode == 0:
            print(f"✓ Model '{model}' downloaded successfully")
            return True
        else:
            print(f"❌ Failed to download: {result.stderr}")
            return False
    except subprocess.TimeoutExpired:
        print("❌ Download timed out")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def test_model(model: str = "llama3.2"):
    """Test model with simple prompt"""
    try:
        import ollama
        print(f"\n🧪 Testing {model}...")
        response = ollama.chat(
            model=model,
            messages=[
                {"role": "user", "content": "Say 'PV Agent System ready' and nothing else."}
            ]
        )
        print(f"✓ Model response: {response['message']['content'].strip()}")
        return True
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False


def main():
    print("=" * 60)
    print("  OLLAMA SETUP CHECK FOR PV MULTI-AGENT SYSTEM")
    print("=" * 60)
    
    # Check Ollama
    print("\n1. Checking Ollama installation...")
    if not check_ollama():
        print("\n📥 To install Ollama:")
        print("   Linux: curl -fsSL https://ollama.com/install.sh | sh")
        print("   macOS: brew install ollama")
        print("   Windows: Download from ollama.com")
        print("\n   After install, start server: ollama serve")
        return 1
    
    # Check models
    print("\n2. Checking available models...")
    models = ["llama3.2", "llama3.1", "mistral", "gemma:2b"]
    available = []
    
    for model in models:
        if check_model(model):
            available.append(model)
    
    if not available:
        print("\n⚠ No LLM models found. Recommended: llama3.2 (fast, capable)")
        download = input("Download llama3.2? (y/n): ").lower() == 'y'
        if download:
            if install_model("llama3.2"):
                available.append("llama3.2")
        else:
            print("\nYou can run the simplified demo without LLM:")
            print("   python demo.py")
            return 0
    
    # Test model
    print(f"\n3. Testing {available[0]}...")
    if test_model(available[0]):
        print("\n✓ All systems ready!")
        print(f"\nRun the full system with:")
        print(f"   python pv_agents.py")
        print(f"   (uses {available[0]} for agent reasoning)")
    else:
        print("\n⚠ Model installed but not working properly")
    
    print("\n" + "=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
