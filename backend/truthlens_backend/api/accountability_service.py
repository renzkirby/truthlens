from django.core.exceptions import ValidationError

from .models import AccountabilityEvent


SENSITIVE_AUDIT_KEY_PARTS = frozenset(
    {
        "api_key",
        "auth_token",
        "file_bytes",
        "password",
        "raw_token",
        "reset_token",
        "secret",
        "token_digest",
        "upload_payload",
        "verification_token",
    }
)


def _validate_json_object(value, field_name):
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValidationError({field_name: "Must be a JSON object."})
    _reject_sensitive_audit_data(value, field_name)
    return value


def _reject_sensitive_audit_data(value, field_name):
    if isinstance(value, dict):
        for key, nested_value in value.items():
            normalized_key = str(key).strip().lower()
            if any(part in normalized_key for part in SENSITIVE_AUDIT_KEY_PARTS):
                raise ValidationError(
                    {field_name: f"Sensitive audit field '{key}' is not permitted."}
                )
            _reject_sensitive_audit_data(nested_value, field_name)
    elif isinstance(value, (list, tuple)):
        for nested_value in value:
            _reject_sensitive_audit_data(nested_value, field_name)
    elif isinstance(value, (bytes, bytearray, memoryview)):
        raise ValidationError({field_name: "Binary data is not permitted."})


def _validate_actor_snapshot(value):
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) != {"id", "username"}:
        raise ValidationError(
            {"actor_snapshot": "Must contain exactly 'id' and 'username'."}
        )

    actor_id = value["id"]
    username = value["username"]
    if not isinstance(actor_id, str) or not actor_id.strip():
        raise ValidationError(
            {"actor_snapshot": "Actor snapshot id must be a nonblank string."}
        )
    if not isinstance(username, str) or not username.strip():
        raise ValidationError(
            {"actor_snapshot": "Actor snapshot username must be a nonblank string."}
        )
    if len(username) > 150:
        raise ValidationError(
            {"actor_snapshot": "Actor snapshot username must be 150 characters or fewer."}
        )

    snapshot = {"id": actor_id.strip(), "username": username}
    _reject_sensitive_audit_data(snapshot, "actor_snapshot")
    return snapshot


def _allows_historical_actor_snapshot(*, action_type, resource_type, capability):
    return (
        action_type == AccountabilityEvent.ActionType.VERDICT_REVISED
        and resource_type == AccountabilityEvent.ResourceType.ADJUDICATION_DECISION
        and capability == "ADJUDICATE"
    )


def record_accountability_event(
    *,
    action_type,
    resource_type,
    resource_id,
    authority_scope,
    actor=None,
    actor_snapshot=None,
    authority_organization=None,
    subject_organization=None,
    capability="",
    previous_state=None,
    new_state=None,
    reason_code="",
    notes="",
    context=None,
):
    valid_scopes = {
        value for value, _label in AccountabilityEvent.AuthorityScope.choices
    }
    if authority_scope not in valid_scopes:
        raise ValidationError({"authority_scope": "Select a valid authority scope."})

    capability = str(capability or "").strip()
    actor_snapshot = _validate_actor_snapshot(actor_snapshot)
    is_authenticated_actor = bool(actor and actor.is_authenticated)

    if actor is not None and not is_authenticated_actor:
        raise ValidationError({"actor": "Actor must be an authenticated user."})

    historical_snapshot_allowed = _allows_historical_actor_snapshot(
        action_type=action_type,
        resource_type=resource_type,
        capability=capability,
    )

    if authority_scope == AccountabilityEvent.AuthorityScope.ORGANIZATION:
        if actor_snapshot is not None and not historical_snapshot_allowed:
            raise ValidationError(
                {
                    "actor_snapshot": (
                        "Historical actor snapshots are not permitted for this action."
                    )
                }
            )
        if not is_authenticated_actor and actor_snapshot is None:
            raise ValidationError({"actor": "Organization authority requires an actor."})
        if actor_snapshot is not None and is_authenticated_actor:
            if actor_snapshot["id"] != str(actor.pk):
                raise ValidationError(
                    {"actor_snapshot": "Actor snapshot does not identify the live actor."}
                )
        if authority_organization is None:
            raise ValidationError(
                {"authority_organization": "Organization authority requires an organization."}
            )
        if not capability:
            raise ValidationError(
                {"capability": "Organization authority requires a capability."}
            )
        if subject_organization is None:
            subject_organization = authority_organization
    elif authority_scope == AccountabilityEvent.AuthorityScope.PLATFORM:
        if actor_snapshot is not None:
            raise ValidationError(
                {"actor_snapshot": "Platform authority requires a live actor."}
            )
        if not is_authenticated_actor:
            raise ValidationError({"actor": "Platform authority requires an actor."})
        if authority_organization is not None:
            raise ValidationError(
                {"authority_organization": "Platform authority cannot use an organization."}
            )
        if not capability:
            raise ValidationError(
                {"capability": "Platform authority requires a capability."}
            )
    elif authority_scope == AccountabilityEvent.AuthorityScope.PERSONAL:
        if actor_snapshot is not None:
            raise ValidationError(
                {"actor_snapshot": "Personal authority requires a live actor."}
            )
        if not is_authenticated_actor:
            raise ValidationError({"actor": "Personal authority requires an actor."})
        if authority_organization is not None:
            raise ValidationError(
                {"authority_organization": "Personal authority cannot use an organization."}
            )
        if capability:
            raise ValidationError(
                {"capability": "Personal authority cannot use a capability."}
            )
    else:
        if actor is not None:
            raise ValidationError({"actor": "System authority cannot use an actor."})
        if actor_snapshot is not None:
            raise ValidationError(
                {"actor_snapshot": "System authority cannot use an actor snapshot."}
            )
        if authority_organization is not None:
            raise ValidationError(
                {"authority_organization": "System authority cannot use an organization."}
            )
        if capability:
            raise ValidationError(
                {"capability": "System authority cannot use a capability."}
            )

    valid_actions = {value for value, _label in AccountabilityEvent.ActionType.choices}
    if action_type not in valid_actions:
        raise ValidationError({"action_type": "Select a valid action type."})
    valid_resources = {
        value for value, _label in AccountabilityEvent.ResourceType.choices
    }
    if resource_type not in valid_resources:
        raise ValidationError({"resource_type": "Select a valid resource type."})

    normalized_resource_id = str(resource_id or "").strip()
    if not normalized_resource_id:
        raise ValidationError({"resource_id": "A resource identifier is required."})

    previous_state = _validate_json_object(previous_state, "previous_state")
    new_state = _validate_json_object(new_state, "new_state")
    context = _validate_json_object(context, "context")
    if actor_snapshot is not None:
        existing_actor_snapshot = context.get("actor_snapshot")
        if existing_actor_snapshot is not None and existing_actor_snapshot != actor_snapshot:
            raise ValidationError(
                {"context": "Context actor snapshot conflicts with the supplied actor snapshot."}
            )
        context = {**context, "actor_snapshot": actor_snapshot}

    actor_username_snapshot = (
        actor_snapshot["username"]
        if actor_snapshot is not None
        else (str(actor.username) if actor is not None else "")
    )

    return AccountabilityEvent.objects.create(
        actor=actor,
        actor_username_snapshot=actor_username_snapshot,
        authority_scope=authority_scope,
        authority_organization=authority_organization,
        authority_organization_name_snapshot=(
            str(authority_organization.name)
            if authority_organization is not None
            else ""
        ),
        subject_organization=subject_organization,
        subject_organization_name_snapshot=(
            str(subject_organization.name) if subject_organization is not None else ""
        ),
        capability=capability,
        action_type=action_type,
        resource_type=resource_type,
        resource_id=normalized_resource_id,
        previous_state=previous_state,
        new_state=new_state,
        reason_code=str(reason_code or ""),
        notes=str(notes or ""),
        context=context,
    )
