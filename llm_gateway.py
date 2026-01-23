#!/usr/bin/env python3
"""
🛡️ TREPAN LLM Gateway (llm_gateway.py)
BYO-LLM (Bring Your Own LLM) - Enterprise Adapter

Supports:
- Groq (current default)
- Azure OpenAI
- AWS Bedrock
- Ollama (local)
- OpenAI-compatible APIs (generic)

Usage:
    from llm_gateway import LLMGateway
    
    gateway = LLMGateway()  # Uses config from llm_config.yaml
    response = gateway.complete("Analyze this code for vulnerabilities...")
"""

import os
import json
import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from pathlib import Path

# Load .env file for API keys
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv not installed, rely on system env vars

logger = logging.getLogger("TREPAN.LLM")


@dataclass
class LLMConfig:
    """Configuration for an LLM provider."""
    provider: str
    model: str
    api_key: Optional[str] = None
    endpoint: Optional[str] = None
    temperature: float = 0.1
    max_tokens: int = 2000
    extra_params: Optional[Dict] = None
    
    def __post_init__(self):
        if self.extra_params is None:
            self.extra_params = {}


@dataclass
class LLMResponse:
    """Standardized response from any LLM provider."""
    content: str
    model: str
    provider: str
    usage: Optional[Dict] = None
    raw_response: Optional[Any] = None


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""
    
    @abstractmethod
    def complete(self, prompt: str, system_prompt: Optional[str] = None, 
                 json_mode: bool = False) -> LLMResponse:
        """Generate a completion from the LLM."""
        pass
    
    @abstractmethod
    def is_available(self) -> bool:
        """Check if this provider is properly configured and available."""
        pass


class GroqProvider(LLMProvider):
    """Provider for Groq Cloud API."""
    
    def __init__(self, config: LLMConfig):
        self.config = config
        self.client = None
        
        # Get API key from config or environment
        api_key = config.api_key or os.getenv("GROQ_API_KEY")
        
        if api_key:
            try:
                from groq import Groq
                self.client = Groq(api_key=api_key)
            except ImportError:
                logger.warning("Groq package not installed: pip install groq")
    
    def is_available(self) -> bool:
        return self.client is not None
    
    def complete(self, prompt: str, system_prompt: Optional[str] = None,
                 json_mode: bool = False) -> LLMResponse:
        if not self.client:
            raise RuntimeError("Groq client not initialized")
        
        messages = [{"role": "system", "content": system_prompt or "You are a security auditor. Analyze code for vulnerabilities."}]
        messages.append({"role": "user", "content": prompt})
        
        kwargs = {
            "messages": messages,
            "model": self.config.model,
            "temperature": float(self.config.temperature),  # Ensure float
            "max_tokens": int(self.config.max_tokens),      # Ensure int
        }
        
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        
        response = self.client.chat.completions.create(**kwargs)
        
        return LLMResponse(
            content=response.choices[0].message.content,
            model=self.config.model,
            provider="groq",
            usage={
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
            } if response.usage else None,
            raw_response=response
        )


class AzureOpenAIProvider(LLMProvider):
    """Provider for Azure OpenAI Service."""
    
    def __init__(self, config: LLMConfig):
        self.config = config
        self.client = None
        
        api_key = config.api_key or os.getenv("AZURE_OPENAI_KEY")
        endpoint = config.endpoint or os.getenv("AZURE_OPENAI_ENDPOINT")
        
        if api_key and endpoint:
            try:
                from openai import AzureOpenAI
                self.client = AzureOpenAI(
                    api_key=api_key,
                    api_version=config.extra_params.get("api_version", "2024-02-01"),
                    azure_endpoint=endpoint
                )
            except ImportError:
                logger.warning("OpenAI package not installed: pip install openai")
    
    def is_available(self) -> bool:
        return self.client is not None
    
    def complete(self, prompt: str, system_prompt: Optional[str] = None,
                 json_mode: bool = False) -> LLMResponse:
        if not self.client:
            raise RuntimeError("Azure OpenAI client not initialized")
        
        messages = [{"role": "system", "content": system_prompt or "You are a helpful assistant."}]
        messages.append({"role": "user", "content": prompt})
        
        kwargs = {
            "model": self.config.model,  # This is the deployment name in Azure
            "messages": messages,
            "temperature": float(self.config.temperature),  # Ensure float
            "max_tokens": int(self.config.max_tokens),      # Ensure int
        }
        
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        
        response = self.client.chat.completions.create(**kwargs)
        
        return LLMResponse(
            content=response.choices[0].message.content,
            model=self.config.model,
            provider="azure_openai",
            usage={
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
            } if response.usage else None,
            raw_response=response
        )


class OpenAIProvider(LLMProvider):
    """Provider for OpenAI API (standard)."""
    
    def __init__(self, config: LLMConfig):
        self.config = config
        self.client = None
        
        api_key = config.api_key or os.getenv("OPENAI_API_KEY")
        
        if api_key:
            try:
                from openai import OpenAI
                self.client = OpenAI(api_key=api_key)
            except ImportError:
                logger.warning("OpenAI package not installed: pip install openai")
    
    def is_available(self) -> bool:
        return self.client is not None
    
    def complete(self, prompt: str, system_prompt: Optional[str] = None,
                 json_mode: bool = False) -> LLMResponse:
        if not self.client:
            raise RuntimeError("OpenAI client not initialized")
        
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        kwargs = {
            "model": self.config.model,
            "messages": messages,
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
        }
        
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        
        response = self.client.chat.completions.create(**kwargs)
        
        return LLMResponse(
            content=response.choices[0].message.content,
            model=self.config.model,
            provider="openai",
            usage={
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
            } if response.usage else None,
            raw_response=response
        )


class OllamaProvider(LLMProvider):
    """Provider for local Ollama instance."""
    
    def __init__(self, config: LLMConfig):
        self.config = config
        self.endpoint = config.endpoint or "http://localhost:11434"
    
    def is_available(self) -> bool:
        import urllib.request
        try:
            with urllib.request.urlopen(f"{self.endpoint}/api/tags", timeout=2):
                return True
        except Exception:
            return False
    
    def complete(self, prompt: str, system_prompt: Optional[str] = None,
                 json_mode: bool = False) -> LLMResponse:
        import urllib.request
        
        full_prompt = prompt
        if system_prompt:
            full_prompt = f"{system_prompt}\n\n{prompt}"
        
        data = {
            "model": self.config.model,
            "prompt": full_prompt,
            "stream": False,
            "options": {
                "temperature": self.config.temperature,
                "num_predict": self.config.max_tokens,
            }
        }
        
        if json_mode:
            data["format"] = "json"
        
        req = urllib.request.Request(
            f"{self.endpoint}/api/generate",
            data=json.dumps(data).encode(),
            headers={"Content-Type": "application/json"}
        )
        
        with urllib.request.urlopen(req, timeout=60) as response:
            result = json.loads(response.read().decode())
        
        return LLMResponse(
            content=result.get("response", ""),
            model=self.config.model,
            provider="ollama",
            usage={
                "prompt_tokens": result.get("prompt_eval_count", 0),
                "completion_tokens": result.get("eval_count", 0),
            },
            raw_response=result
        )


class OpenAICompatibleProvider(LLMProvider):
    """Provider for any OpenAI-compatible API (vLLM, LM Studio, etc.)."""
    
    def __init__(self, config: LLMConfig):
        self.config = config
        self.client = None
        
        api_key = config.api_key or os.getenv("OPENAI_COMPATIBLE_KEY") or "dummy"
        endpoint = config.endpoint
        
        if endpoint:
            try:
                from openai import OpenAI
                self.client = OpenAI(
                    api_key=api_key,
                    base_url=endpoint
                )
            except ImportError:
                logger.warning("OpenAI package not installed: pip install openai")
    
    def is_available(self) -> bool:
        return self.client is not None
    
    def complete(self, prompt: str, system_prompt: Optional[str] = None,
                 json_mode: bool = False) -> LLMResponse:
        if not self.client:
            raise RuntimeError("OpenAI-compatible client not initialized")
        
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        kwargs = {
            "model": self.config.model,
            "messages": messages,
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
        }
        
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        
        response = self.client.chat.completions.create(**kwargs)
        
        return LLMResponse(
            content=response.choices[0].message.content,
            model=self.config.model,
            provider="openai_compatible",
            usage={
                "prompt_tokens": getattr(response.usage, 'prompt_tokens', 0),
                "completion_tokens": getattr(response.usage, 'completion_tokens', 0),
            } if response.usage else None,
            raw_response=response
        )


# Provider registry
PROVIDERS = {
    "groq": GroqProvider,
    "azure_openai": AzureOpenAIProvider,
    "openai": OpenAIProvider,
    "ollama": OllamaProvider,
    "openai_compatible": OpenAICompatibleProvider,
}


class LLMGateway:
    """
    Main gateway class for LLM access.
    Configurable via llm_config.yaml or environment variables.
    """
    
    def __init__(self, config_path: Optional[str] = None):
        self.config = self._load_config(config_path)
        self.provider = self._create_provider()
    
    def _load_config(self, config_path: Optional[str]) -> LLMConfig:
        """Load configuration from YAML file or use defaults."""
        
        # Default config path
        if config_path is None:
            for path in ["llm_config.yaml", "llm_config.json"]:
                if os.path.exists(path):
                    config_path = path
                    break
        
        # Load from file if exists
        if config_path and os.path.exists(config_path):
            try:
                if config_path.endswith('.yaml') or config_path.endswith('.yml'):
                    import yaml
                    with open(config_path, 'r', encoding='utf-8') as f:
                        data = yaml.safe_load(f) or {}
                else:
                    with open(config_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                
                return LLMConfig(
                    provider=data.get('provider', 'groq'),
                    model=data.get('model', 'llama-3.1-70b-versatile'),
                    api_key=data.get('api_key'),
                    endpoint=data.get('endpoint'),
                    temperature=data.get('temperature', 0.1),
                    max_tokens=data.get('max_tokens', 2000),
                    extra_params=data.get('extra_params', {})
                )
            except Exception as e:
                logger.warning(f"Failed to load config: {e}, using defaults")
        
        # Default: Groq with environment variable
        return LLMConfig(
            provider="groq",
            model="llama-3.1-70b-versatile"
        )
    
    def _create_provider(self) -> LLMProvider:
        """Create the appropriate provider based on config."""
        provider_class = PROVIDERS.get(self.config.provider)
        
        if not provider_class:
            raise ValueError(f"Unknown provider: {self.config.provider}. "
                           f"Available: {list(PROVIDERS.keys())}")
        
        provider = provider_class(self.config)
        
        if not provider.is_available():
            logger.warning(f"Provider {self.config.provider} is not available, "
                          f"check API keys and dependencies")
        
        return provider
    
    def complete(self, prompt: str, system_prompt: Optional[str] = None,
                 json_mode: bool = False) -> LLMResponse:
        """
        Generate a completion using the configured LLM.
        
        Args:
            prompt: The user prompt
            system_prompt: Optional system prompt for context
            json_mode: If True, request JSON-formatted response
        
        Returns:
            LLMResponse with content and metadata
        """
        return self.provider.complete(prompt, system_prompt, json_mode)
    
    def audit_code(self, code: str, filename: str = "code") -> Dict:
        """
        Convenience method for security audit (used by Red Team).
        
        Returns:
            Dict with 'status' (SAFE/DANGER) and 'issue'/'fix_instruction'
        """
        system_prompt = """You are an Elite DevSecOps Security Sentinel named Trepan.
Your goal is to find and fix security vulnerabilities.

🚨 AUTOMATIC DANGER FLAGS (If you see ANY of these, status MUST be "DANGER"):
- String concatenation with file paths (e.g., "/path/" + filename)
- os.path.join WITHOUT os.path.realpath validation
- SQL queries with string formatting or concatenation
- os.system() or subprocess with shell=True
- eval(), exec(), or compile() with user input
- Hardcoded passwords, API keys, or secrets
- request.args/form used directly in file operations

SECURITY FIXES REQUIRED:
1. FILE PATHS: Use os.path.realpath() + startswith() check
2. SQL: Use parameterized queries (?, %s)
3. COMMANDS: Use subprocess with shell=False and list args
4. SECRETS: Use os.environ.get()

OUTPUT JSON ONLY:
{
    "status": "DANGER" or "SAFE",
    "issue": "The vulnerability found",
    "fix_instruction": "How to fix it",
    "fixed_code": "The COMPLETE fixed code with os.path.realpath() for file operations"
}"""
        
        prompt = f"TARGET: {filename}\nCODE:\n{code}"
        
        try:
            # NOTE: json_mode=False because not all models support it (Groq 400 error)
            response = self.complete(prompt, system_prompt, json_mode=False)
            
            # Manually extract JSON from response
            content = response.content.strip()
            # Try to find JSON in the response
            if "{" in content and "}" in content:
                json_start = content.find("{")
                json_end = content.rfind("}") + 1
                json_str = content[json_start:json_end]
                return json.loads(json_str)
            return {"status": "ERROR", "issue": "No JSON in response"}
        except json.JSONDecodeError:
            return {"status": "ERROR", "issue": "Failed to parse LLM response"}
        except Exception as e:
            return {"status": "ERROR", "issue": str(e)}
    
    def is_available(self) -> bool:
        """Check if the gateway is properly configured and available."""
        return self.provider.is_available()
    
    def get_provider_info(self) -> Dict:
        """Get information about the current provider configuration."""
        return {
            "provider": self.config.provider,
            "model": self.config.model,
            "endpoint": self.config.endpoint,
            "available": self.provider.is_available()
        }


# --- CLI for testing ---
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="🛡️ Trepan LLM Gateway")
    parser.add_argument("--config", "-c", help="Path to config file")
    parser.add_argument("--test", action="store_true", help="Run a test query")
    parser.add_argument("--info", action="store_true", help="Show provider info")
    
    args = parser.parse_args()
    
    gateway = LLMGateway(config_path=args.config)
    
    if args.info:
        info = gateway.get_provider_info()
        print(f"\n🔌 LLM Gateway Configuration:")
        print(f"   Provider: {info['provider']}")
        print(f"   Model: {info['model']}")
        print(f"   Endpoint: {info['endpoint'] or 'default'}")
        print(f"   Available: {'✅' if info['available'] else '❌'}")
    
    if args.test:
        print("\n🧪 Running test query...")
        try:
            response = gateway.complete("Say 'Hello from Trepan!' in exactly those words.")
            print(f"✅ Response: {response.content}")
            print(f"   Model: {response.model}")
            print(f"   Provider: {response.provider}")
        except Exception as e:
            print(f"❌ Test failed: {e}")
