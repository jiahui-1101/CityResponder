"""Policy-driven supporting-channel evaluation for future confirmation."""

from datetime import datetime, timezone
from typing import Literal, Protocol

from app.fusion.schemas import (
    FusionEvaluation,
    SupportingChannelDecision,
    SupportingChannelResult,
)


ChannelName = Literal["S", "T", "V", "H"]
CHANNELS: tuple[ChannelName, ...] = ("S", "T", "V", "H")


class SupportingChannelPolicy(Protocol):
    """Future source-backed rule for deciding whether a channel supports."""

    def evaluate(
        self,
        channel: ChannelName,
        channel_evaluation: object,
    ) -> SupportingChannelDecision:
        """Return a deterministic supporting/not-supporting decision."""


def evaluate_supporting_channels(
    evaluation: FusionEvaluation,
    policy: SupportingChannelPolicy | None = None,
) -> SupportingChannelResult:
    """Evaluate support only through an explicit policy; never infer it."""

    evaluated_at = datetime.now(timezone.utc)
    if policy is None:
        decisions = [
            SupportingChannelDecision(
                channel=channel,
                decision="not_evaluated",
                score=getattr(evaluation, channel.lower()).score,
                reason="supporting-channel policy is not configured",
                audit_references=getattr(evaluation, channel.lower()).source_references,
            )
            for channel in CHANNELS
        ]
        return _result(
            status="not_evaluated",
            decisions=decisions,
            evaluation=evaluation,
            evaluated_at=evaluated_at,
        )

    decisions: list[SupportingChannelDecision] = []
    for channel in CHANNELS:
        channel_evaluation = getattr(evaluation, channel.lower())
        try:
            decision = policy.evaluate(channel, channel_evaluation)
            if decision.channel != channel:
                raise ValueError("policy returned a decision for the wrong channel")
            decisions.append(
                decision.model_copy(
                    update={
                        "score": channel_evaluation.score,
                        "audit_references": channel_evaluation.source_references,
                    }
                )
            )
        except Exception as exc:
            decisions.append(
                SupportingChannelDecision(
                    channel=channel,
                    decision="not_evaluated",
                    score=channel_evaluation.score,
                    reason=f"supporting-channel policy failed: {exc}",
                    audit_references=channel_evaluation.source_references,
                )
            )
    status = (
        "evaluated"
        if all(decision.decision != "not_evaluated" for decision in decisions)
        else "not_evaluated"
    )
    return _result(
        status=status,
        decisions=decisions,
        evaluation=evaluation,
        evaluated_at=evaluated_at,
    )


def _result(
    *,
    status: Literal["evaluated", "not_evaluated"],
    decisions: list[SupportingChannelDecision],
    evaluation: FusionEvaluation,
    evaluated_at: datetime,
) -> SupportingChannelResult:
    supporting = [
        decision.channel
        for decision in decisions
        if decision.decision == "supporting"
    ]
    non_supporting = [
        decision.channel
        for decision in decisions
        if decision.decision == "not_supporting"
    ]
    not_evaluated = [
        decision.channel
        for decision in decisions
        if decision.decision == "not_evaluated"
    ]
    return SupportingChannelResult(
        status=status,
        supporting_channels=supporting,
        non_supporting_channels=non_supporting,
        not_evaluated_channels=not_evaluated,
        supporting_count=len(supporting) if not not_evaluated else None,
        decisions=decisions,
        audit_references=evaluation.audit_references,
        evaluated_at=evaluated_at,
    )
