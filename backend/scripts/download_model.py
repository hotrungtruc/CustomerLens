import os
import sys
from pathlib import Path

def main():
    import io
    # Fix for Windows charmap codec error when PyTorch tries to print emojis like ❌
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

    try:
        import torch
        import onnx
        from transformers import AutoModel
        from huggingface_hub import snapshot_download
    except ImportError:
        print("Missing required libraries. Please install them first:")
        print("pip install torch transformers onnx huggingface_hub timm")
        sys.exit(1)

    print("Downloading and loading the model 'minchul/cvlface_adaface_ir18_webface4m'...")
    try:
        # Download the repo snapshot to local cache to satisfy custom code requirements
        model_path = snapshot_download("minchul/cvlface_adaface_ir18_webface4m")
        sys.path.insert(0, model_path)
        
        # Change cwd to model_path because the custom code hardcodes 'pretrained_model/model.yaml'
        original_cwd = os.getcwd()
        os.chdir(model_path)
        
        try:
            # Patch PreTrainedModel to avoid 'all_tied_weights_keys' bug in newer transformers with this model
            from transformers.modeling_utils import PreTrainedModel
            if not hasattr(PreTrainedModel, 'all_tied_weights_keys'):
                PreTrainedModel.all_tied_weights_keys = property(lambda self: [])

            from transformers import AutoModel
            # Load using the standard approach as requested by user
            model = AutoModel.from_pretrained("minchul/cvlface_adaface_ir18_webface4m", trust_remote_code=True, torch_dtype="auto")
        finally:
            os.chdir(original_cwd)
    except Exception as e:
        print(f"Failed to load model from huggingface: {e}")
        print("If you encounter 'No module named timm', run: pip install timm")
        sys.exit(1)
        
    model.eval()

    # AdaFace models expect 112x112 images
    dummy_input = torch.randn(1, 3, 112, 112)

    base_dir = Path(__file__).resolve().parent.parent
    models_dir = base_dir / "models"
    
    if not models_dir.exists():
        models_dir.mkdir(parents=True, exist_ok=True)
        
    dest_path = models_dir / "adaface_ir18.onnx"
    temp_path = models_dir / "temp_adaface_ir18.onnx"
    data_path = "adaface_ir18.onnx.data"

    print(f"Exporting model to temporary ONNX file {temp_path}...")
    try:
        torch.onnx.export(
            model, 
            dummy_input, 
            str(temp_path), 
            export_params=True, 
            do_constant_folding=True, 
            input_names=['input'], 
            output_names=['output']
        )
    except Exception as e:
        print(f"Failed to export model to ONNX: {e}")
        sys.exit(1)

    print(f"Saving ONNX model with external data to {dest_path} and {dest_path.parent / data_path}...")
    try:
        onnx_model = onnx.load(str(temp_path))
        # Save the model and its weights into separate files
        onnx.save_model(
            onnx_model, 
            str(dest_path), 
            save_as_external_data=True, 
            all_tensors_to_one_file=True, 
            location=data_path, 
            size_threshold=1024, # Forces almost all tensors to go to the external data file
            convert_attribute=False
        )
        # Remove the temporary file
        os.remove(str(temp_path))
        print("Successfully exported model to ONNX with external data.")
    except Exception as e:
        print(f"Failed to split ONNX model: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
