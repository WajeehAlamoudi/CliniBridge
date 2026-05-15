import json
from typing import Any, Callable, Dict, Optional

from openai import OpenAI
from ChatAgent.chat_agent_config import CHAT_AGENT_CONFIG
from ChatAgent.chat_agent_utils import flat_system_prompt_sections

import logging
logger = logging.getLogger(__name__)


class ChatAgent:
    def __init__(
            self,
            api_key: Optional[str] = None,
            structured_system_message: Optional[Dict[str, Any]] = None,
            max_tokens: Optional[int] = CHAT_AGENT_CONFIG["max_tokens"],
            max_tool_use: Optional[int] = CHAT_AGENT_CONFIG['max_tool_use'],
            default_model_name=CHAT_AGENT_CONFIG['default_model_name'],
            reset_on_model_switch: Optional[bool] = False,
            json_mode: bool = False,
            temperature: Optional[float] = None,
            top_p: Optional[float] = None,
            frequency_penalty: Optional[float] = None,
    ) -> None:

        # API key validation
        if not isinstance(api_key, str) or not api_key.strip():
            raise ValueError("api_key must be non-empty string")
        else:
            self.api_key = api_key

        self.event_handler = None

        # models and defaults
        self.models = CHAT_AGENT_CONFIG['models']
        self.default_model_name = default_model_name
        self.active_model_name = self.default_model_name
        self.model = self.models[self.default_model_name]

        # other config values
        self.max_tool_use = max_tool_use
        self.base_url = CHAT_AGENT_CONFIG['base_url']
        self.json_mode = json_mode
        self.temperature = temperature
        self.top_p = top_p
        self.frequency_penalty = frequency_penalty

        # structured system message fallback
        if structured_system_message is None:
            structured_system_message = {}
        self.structured_system_message = structured_system_message["chat_agent_system_prompt"]

        # reset flag and max tokens
        self.reset_on_model_switch = reset_on_model_switch
        self.max_tokens = max_tokens

        # flatten system message
        self.flat_system_message = flat_system_prompt_sections(self.structured_system_message)

        self.chat_history = [
            {"role": "system", "content": self.flat_system_message}
        ]

        self.functions: Dict[str, Dict[str, Any]] = {}
        self.last_token_usage = None
        self.total_token_usage = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }

        self._rebuild_client()

        logger.info(
            f"ChatAgent initialized with model='{self.model}', "
            f"reset_on_model_switch={self.reset_on_model_switch}, "
            f"max_tool_use={self.max_tool_use}, max_tokens={self.max_tokens}"
        )

    # -------------------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------------------

    def set_event_handler(self, event_handler) -> None:
        self.event_handler = event_handler

    def _emit_event(self, role: str, content: str) -> None:
        if not self.event_handler:
            return

        try:
            self.event_handler(role=role, content=content)
        except Exception as exc:
            logger.error(f"Failed to emit chat event '{role}': {exc}")

    def _call_model(self, allow_tools: bool):
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": self.chat_history,
            "max_tokens": self.max_tokens,
        }

        if allow_tools and self.functions:
            payload["tools"] = self._build_tools_payload()
            payload["tool_choice"] = "auto"

        if self.json_mode:
            payload["response_format"] = {"type": "json_object"}

        if self.temperature is not None:
            payload["temperature"] = self.temperature

        if self.top_p is not None:
            payload["top_p"] = self.top_p

        if self.frequency_penalty is not None:
            payload["frequency_penalty"] = self.frequency_penalty

        response = self.client.chat.completions.create(**payload)
        self._save_token_usage(response)
        return response

    def _force_final_answer(self) -> str:
        response = self._call_model(allow_tools=False)

        if not getattr(response, "choices", None):
            raise ValueError("Forced final answer returned no choices")

        final_text = (response.choices[0].message.content or "").strip()
        if not final_text:
            raise ValueError("Forced final answer was empty")

        self.chat_history.append({
            "role": "assistant",
            "content": final_text,
        })
        return final_text

    def _build_tools_payload(self) -> list:
        return [
            {"type": "function", "function": item["spec"]}
            for item in self.functions.values()
        ]

    def _safe_execute_tool(self, tool_name: str, tool_args: Dict[str, Any]) -> Any:
        if tool_name not in self.functions:
            raise ValueError(f"Tool '{tool_name}' is not registered")

        logger.info(f"Executing tool '{tool_name}' args={tool_args}")
        return self.functions[tool_name]["function"](**tool_args)

    def _save_token_usage(self, response: Any) -> None:
        usage = getattr(response, "usage", None)
        self.last_token_usage = usage

        if not usage:
            return

        prompt_tokens = getattr(usage, "prompt_tokens", 0) or 0
        completion_tokens = getattr(usage, "completion_tokens", 0) or 0
        total_tokens = getattr(usage, "total_tokens", 0) or 0

        self.total_token_usage["prompt_tokens"] += prompt_tokens
        self.total_token_usage["completion_tokens"] += completion_tokens
        self.total_token_usage["total_tokens"] += total_tokens

    @staticmethod
    def _serialize_tool_call(tool_call: Any) -> Dict[str, Any]:
        return {
            "id": getattr(tool_call, "id", ""),
            "type": "function",
            "function": {
                "name": getattr(tool_call.function, "name", ""),
                "arguments": getattr(tool_call.function, "arguments", "{}"),
            }
        }

    @staticmethod
    def _serialize_tool_result(result: Any) -> str:
        if isinstance(result, str):
            return result

        try:
            return json.dumps(result, ensure_ascii=False, default=str)
        except Exception:
            return str(result)

    @staticmethod
    def _try_parse_text_tool_call(text: str) -> Optional[Dict[str, Any]]:
        if not text or not isinstance(text, str):
            return None

        stripped = text.strip()
        if not stripped.startswith("{") or not stripped.endswith("}"):
            return None

        try:
            data = json.loads(stripped)
        except Exception:
            return None

        if not isinstance(data, dict):
            return None

        name = data.get("name")
        parameters = data.get("parameters")

        if not isinstance(name, str) or not isinstance(parameters, dict):
            return None

        return {
            "name": name,
            "parameters": parameters,
        }

    def test_connection(self) -> tuple[bool, Optional[str]]:
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "user", "content": "ping"}
                ],
                max_tokens=16,
            )
            return bool(getattr(response, "choices", None)), None
        except Exception as exc:
            logger.error(f"ChatAgent connection test failed: {exc}")
            return False, str(exc)

    def _rebuild_client(self) -> None:
        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            default_headers={
                "HTTP-Referer": CHAT_AGENT_CONFIG["http_referer"],
                "X-Title": CHAT_AGENT_CONFIG["app_title"],
            }
        )

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    def set_api_key(self, api_key: str) -> None:
        if not isinstance(api_key, str) or not api_key.strip():
            raise ValueError("api_key must be a non-empty string")

        self.api_key = api_key.strip()
        self._rebuild_client()

    def clear_chat_history(self) -> None:
        self.chat_history = [
            {"role": "system", "content": self.flat_system_message}
        ]
        logger.info("Chat history cleared; system message preserved")

    def load_chat_history(self, messages: list[Dict[str, Any]]) -> None:
        self.chat_history = [
            {"role": "system", "content": self.flat_system_message}
        ]

        for message in messages:
            role = message.get("role")
            content = message.get("content")

            if role not in {"user", "assistant"}:
                continue

            if not isinstance(content, str) or not content.strip():
                continue

            self.chat_history.append({
                "role": role,
                "content": content,
            })

        logger.info("Chat history loaded from stored session messages")

    def replace_system_message(self, structured_system_message: Dict[str, Any]) -> None:
        if not isinstance(structured_system_message, dict):
            raise ValueError("structured_system_message must be a dictionary")

        if "chat_agent_system_prompt" not in structured_system_message:
            raise ValueError("structured_system_message must contain 'chat_agent_system_prompt'")

        self.structured_system_message = structured_system_message["chat_agent_system_prompt"]
        self.flat_system_message = flat_system_prompt_sections(self.structured_system_message)

        if self.chat_history and self.chat_history[0].get("role") == "system":
            self.chat_history[0]["content"] = self.flat_system_message
        else:
            self.chat_history.insert(
                0,
                {
                    "role": "system",
                    "content": self.flat_system_message,
                },
            )

        logger.info("System message replaced; existing chat history preserved")

    def set_model(self, model_name: str, reset_history: Optional[bool] = None) -> None:
        if not isinstance(model_name, str) or model_name not in self.models:
            raise ValueError(f"Unknown model key: {model_name}")

        self.active_model_name = model_name
        self.model = self.models[model_name]

        should_reset = self.reset_on_model_switch if reset_history is None else reset_history
        if should_reset:
            self.clear_chat_history()

        logger.info(
            f"Active model switched to '{self.model}' (key='{self.active_model_name}'), "
            f"reset_history={should_reset}"
        )

    def update_system_message(self, knowledge_base: list):
        if not isinstance(self.flat_system_message, str) or not self.flat_system_message.strip():
            raise ValueError("flat_system_message must be a non-empty string")

        self.structured_system_message["CONTEXT"]["KNOWLEDGE BASE"]["Database Schema"] = knowledge_base
        self.flat_system_message = flat_system_prompt_sections(self.structured_system_message)

        if self.chat_history and self.chat_history[0].get("role") == "system":
            self.chat_history[0]["content"] = self.flat_system_message
        else:
            self.chat_history.insert(0, {"role": "system", "content": self.flat_system_message})

    def ask(self, input_prompt: str) -> str:

        if not isinstance(input_prompt, str) or not input_prompt.strip():
            raise ValueError("input_prompt must be a non-empty string")

        self.chat_history.append({"role": "user", "content": input_prompt})
        tool_calls_used = 0

        logger.info(f"User ask: {input_prompt[:60]}")

        try:
            while True:
                response = self._call_model(allow_tools=True)

                if not getattr(response, "choices", None):
                    raise ValueError("Model returned no choices")

                message = response.choices[0].message
                tool_calls = getattr(message, "tool_calls", None)

                # Native tool calls
                if tool_calls:
                    if tool_calls_used >= self.max_tool_use:
                        logger.warning("Max tool usage reached before processing new tool calls")
                        return self._force_final_answer()

                    self.chat_history.append({
                        "role": "assistant",
                        "content": message.content or "",
                        "tool_calls": [self._serialize_tool_call(tc) for tc in tool_calls],
                    })

                    for tc in tool_calls:
                        if tool_calls_used >= self.max_tool_use:
                            logger.warning("Max tool usage reached during tool execution loop")
                            return self._force_final_answer()

                        tool_name = getattr(tc.function, "name", "")
                        raw_arguments = getattr(tc.function, "arguments", "") or "{}"

                        try:
                            tool_args = json.loads(raw_arguments)
                            if not isinstance(tool_args, dict):
                                raise ValueError("Tool arguments must decode to a JSON object")

                            if tool_name == "EXECUTE_SQL":
                                sql_code = tool_args.get("sql_code", "")
                                if sql_code:
                                    self._emit_event(
                                        role="tool_call",
                                        content=f"```sql\n{sql_code}\n```",
                                    )
                            else:
                                self._emit_event(
                                    role="tool_call",
                                    content=self._serialize_tool_result({
                                        "name": tool_name,
                                        "arguments": tool_args,
                                    }),
                                )

                            try:
                                tool_result = self._safe_execute_tool(tool_name, tool_args)
                            except Exception as exc:
                                logger.error(f"Tool '{tool_name}' execution failed: {exc}")
                                tool_result = {
                                    "success": False,
                                    "error": f"Tool '{tool_name}' execution failed: {exc}",
                                }

                        except Exception as exc:
                            logger.error(f"Invalid tool arguments for '{tool_name}': {exc}")
                            tool_result = {
                                "success": False,
                                "error": f"Invalid tool arguments for '{tool_name}': {exc}",
                            }

                        self._emit_event(
                            role="tool_result",
                            content=self._serialize_tool_result(tool_result),
                        )

                        tool_calls_used += 1

                        self.chat_history.append({
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "name": tool_name,
                            "content": self._serialize_tool_result(tool_result),
                        })

                    continue

                # Fallback: model printed fake JSON tool call instead of using native tool call
                final_text = (message.content or "").strip()
                parsed_tool_call = self._try_parse_text_tool_call(final_text)

                if parsed_tool_call and tool_calls_used < self.max_tool_use:
                    tool_name = parsed_tool_call["name"]
                    tool_args = parsed_tool_call["parameters"]

                    logger.warning(
                        f"Model returned text-based tool call fallback for '{tool_name}'"
                    )

                    self.chat_history.append({
                        "role": "assistant",
                        "content": final_text,
                    })

                    self._emit_event(
                        role="tool_call",
                        content=self._serialize_tool_result({
                            "name": tool_name,
                            "arguments": tool_args,
                        }),
                    )

                    try:
                        tool_result = self._safe_execute_tool(tool_name, tool_args)
                    except Exception as exc:
                        logger.error(f"Fallback tool '{tool_name}' execution failed: {exc}")
                        tool_result = {
                            "success": False,
                            "error": f"Tool '{tool_name}' execution failed: {exc}",
                        }

                    self._emit_event(
                        role="tool_result",
                        content=self._serialize_tool_result(tool_result),
                    )

                    tool_calls_used += 1

                    self.chat_history.append({
                        "role": "tool",
                        "tool_call_id": f"fallback_{tool_calls_used}",
                        "name": tool_name,
                        "content": self._serialize_tool_result(tool_result),
                    })

                    continue

                if not final_text:
                    raise ValueError("Model returned an empty final response")

                self.chat_history.append({
                    "role": "assistant",
                    "content": final_text,
                })

                logger.info(f"Agent response ready. tokens={self.total_token_usage['total_tokens']}")

                return final_text

        except Exception as exc:
            error_message = f"Agent failed: {exc}"
            logger.error(error_message)

            self.chat_history.append({
                "role": "assistant",
                "content": error_message,
            })
            return error_message

    def register_function(self, func: Callable, description: str, parameters: Optional[Dict[str, Any]] = None,) -> None:
        if not callable(func):
            raise ValueError("func must be callable")

        if not isinstance(description, str) or not description.strip():
            raise ValueError("description must be a non-empty string")

        if parameters is None:
            parameters = {
                "type": "object",
                "properties": {
                    "input": {
                        "type": "string",
                        "description": "General-purpose input"
                    }
                },
                "required": ["input"]
            }

        if not isinstance(parameters, dict) or parameters.get("type") != "object":
            raise ValueError("parameters must be a valid JSON schema object")

        self.functions[func.__name__] = {
            "function": func,
            "spec": {
                "name": func.__name__,
                "description": description,
                "parameters": parameters,
            }
        }

        logger.info(f"Registered function '{func.__name__}'")

    def unregister_function(self, function_name: str) -> None:
        if not isinstance(function_name, str) or not function_name.strip():
            raise ValueError("function_name must be a non-empty string")

        if function_name in self.functions:
            del self.functions[function_name]
            logger.info(f"Unregistered function '{function_name}'")

    def get_available_models(self) -> Dict[str, str]:
        return dict(self.models)

    def get_current_model(self) -> Dict[str, str]:
        return {
            "active_model_key": self.active_model_name,
            "model": self.model,
        }

    def get_token_usage(self) -> Dict[str, Optional[Dict[str, int]]]:
        last_usage = None

        if self.last_token_usage:
            last_usage = {
                "prompt_tokens": getattr(self.last_token_usage, "prompt_tokens", 0),
                "completion_tokens": getattr(self.last_token_usage, "completion_tokens", 0),
                "total_tokens": getattr(self.last_token_usage, "total_tokens", 0),
            }

        return {
            "last": last_usage,
            "accumulated": dict(self.total_token_usage),
        }
