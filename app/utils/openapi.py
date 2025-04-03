from typing import Optional, Dict, List

def create_openapi_extra(
    detail_params: Optional[Dict] = None,
    client_extra: Optional[Dict] = None,
    contexts: Optional[List] = None,
    utterance: Optional[str] = None,
) -> Dict:
    """detail_params, client_extra, contexts를 받아
    OpenAPI 스키마에 맞게 변환하며, 각각을 default로 설정한다.
    예시:
    >>> detail_params = {
    ...     "Cafeteria": {
    ...         "origin": "산돌",
    ...         "value": "산돌식당"
    ...     }
    ... }
    """
    if detail_params is None:
        detail_params = {}
    if client_extra is None:
        client_extra = {}
    if contexts is None:
        contexts = []
    if utterance is None:
        utterance = ""

    detail_params_schema = {
        "type": "object",
        "additionalProperties": {
            "type": "object",
            "properties": {
                "origin": {"type": "string"},
                "value": {
                    "oneOf": [
                        {"type": "string"},
                        {"type": "object"},
                    ]
                },
                "group_name": {"type": "string"},
            },
        },
        # detail_params를 그대로 default로 설정
        "default": detail_params,
    }
    default_params = {}
    if detail_params:
        default_params = {key: value["value"] for key, value in detail_params.items()}

    client_extra_schema = {
        "type": "object",
        "additionalProperties": {"type": "string"},
        # client_extra를 그대로 default로 설정
        "default": client_extra,
    }

    contexts_schema = {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "lifespan": {"type": "integer"},
                "ttl": {"type": ["integer", "null"]},
                "params": {
                    "type": "object",
                    "additionalProperties": {
                        "oneOf": [
                            {"type": "string"},
                            {
                                "type": "object",
                                "properties": {
                                    "value": {"type": "string"},
                                    "resolved_value": {"type": "string"},
                                },
                            },
                        ],
                    },
                },
            },
        },
        # contexts를 그대로 default로 설정
        "default": contexts,
    }

    return {
        "requestBody": {
            "required": True,
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "properties": {
                            "intent": {
                                "type": "object",
                                "properties": {
                                    "id": {"type": "string"},
                                    "name": {"type": "string"},
                                    "extra": {
                                        "type": "object",
                                        "properties": {
                                            "reason": {"type": "object"},
                                            "matched_knowledges": {
                                                "type": "array",
                                                "items": {
                                                    "type": "object",
                                                    "properties": {
                                                        "answer": {"type": "string"},
                                                        "question": {"type": "string"},
                                                        "categories": {
                                                            "type": "array",
                                                            "items": {"type": "string"},
                                                        },
                                                        "landing_url": {
                                                            "type": "string"
                                                        },
                                                        "image_url": {"type": "string"},
                                                    },
                                                },
                                            },
                                        },
                                    },
                                },
                                "required": ["id", "name"],
                            },
                            "user_request": {
                                "type": "object",
                                "properties": {
                                    "timezone": {
                                        "type": "string",
                                        "default": "Asia/Seoul",
                                    },
                                    "block": {
                                        "type": "object",
                                        "additionalProperties": True,
                                    },
                                    "utterance": {
                                        "type": "string",
                                        "default": utterance,
                                    },
                                    "lang": {"type": "string", "default": "ko"},
                                    "user": {
                                        "type": "object",
                                        "properties": {
                                            "id": {
                                                "type": "string",
                                                "default": "test_user_id",
                                            },
                                            "type": {
                                                "type": "string",
                                                "default": "botUserKey",
                                            },
                                            "properties": {
                                                "type": "object",
                                                "additionalProperties": True,
                                            },
                                        },
                                        "required": ["id", "type"],
                                    },
                                    "params": {
                                        "type": ["object", "null"],
                                        "additionalProperties": True,
                                    },
                                    "callback_url": {"type": ["string", "null"]},
                                },
                                "required": [
                                    "timezone",
                                    "block",
                                    "utterance",
                                    "lang",
                                    "user",
                                ],
                            },
                            "bot": {
                                "type": "object",
                                "properties": {
                                    "id": {"type": "string", "default": "test_bot_id"},
                                    "name": {
                                        "type": "string",
                                        "default": "test_bot_name",
                                    },
                                },
                                "required": ["id", "name"],
                            },
                            "action": {
                                "type": "object",
                                "properties": {
                                    "id": {"type": "string"},
                                    "name": {"type": "string"},
                                    "params": {
                                        "type": "object",
                                        "additionalProperties": {"type": "string"},
                                        "default": default_params,
                                    },
                                    "detailParams": detail_params_schema,
                                    "clientExtra": client_extra_schema,
                                },
                                "required": ["id", "name", "params"],
                            },
                            "contexts": contexts_schema,
                            "params": {
                                "type": "object",
                                "additionalProperties": {"type": "string"},
                            },
                            "timezone": {"type": "string"},
                            "user": {
                                "type": "object",
                                "properties": {
                                    "id": {"type": "string"},
                                    "type": {"type": "string"},
                                    "properties": {
                                        "type": "object",
                                        "additionalProperties": True,
                                    },
                                },
                                "required": ["id", "type"],
                            },
                            "utterance": {"type": "string"},
                            "value": {
                                "type": "object",
                                "additionalProperties": {"type": "string"},
                            },
                        },
                        "required": ["intent", "user_request", "bot", "action"],
                    }
                }
            },
        }
    }
