# Nemotron 3 Nano `nano_v3` reasoning-parser plugin for vLLM.
# Source of truth: the NVIDIA HF model repo (fetched 2026-07-17), public/ungated:
#   https://huggingface.co/nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16/resolve/main/nano_v3_reasoning_parser.py
# Baked into the Modal image by runtime/modal_app.py and passed via
#   --reasoning-parser nano_v3 --reasoning-parser-plugin nano_v3_reasoning_parser.py
# If you bump vLLM and it ships `nano_v3` built-in, you can drop this file and set
# USE_REASONING_PLUGIN=False in modal_app.py. Keep in sync with the recipe.
from vllm.reasoning.abs_reasoning_parsers import ReasoningParserManager
from vllm.reasoning.deepseek_r1_reasoning_parser import DeepSeekR1ReasoningParser


@ReasoningParserManager.register_module("nano_v3")
class NanoV3ReasoningParser(DeepSeekR1ReasoningParser):
    def extract_reasoning(self, model_output, request):
        reasoning_content, final_content = super().extract_reasoning(
            model_output, request
        )
        if (
            hasattr(request, "chat_template_kwargs")
            and request.chat_template_kwargs
            and request.chat_template_kwargs.get("enable_thinking") is False
            and final_content is None
        ):
            reasoning_content, final_content = final_content, reasoning_content

        return reasoning_content, final_content
