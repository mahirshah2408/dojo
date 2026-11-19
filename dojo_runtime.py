"""Dojo phase transitions and idea-pool decisions. The CLI remains in bracket.py."""
import copy
import difflib
from pathlib import Path
import re

import dojo_protocol as p

PHASES = ("spawn", "attack", "defend", "candidate", "review", "judge", "evaluate", "recheck", "final")
TERMINAL = ("completed", "deferred")


def text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise p.ProtocolError(name + " must be nonempty text")
    return value


def strings(value, name, nonempty=False):
    if not isinstance(value, list) or any(not isinstance(v, str) or not v.strip() for v in value):
        raise p.ProtocolError(name + " must be a list of nonempty strings")
    if nonempty and not value:
        raise p.ProtocolError(name + " needs evidence or conditions")
    return value


def current_round(state):
    return None if state["champion"] else state["rounds"][-1]


def match(state, mid):
    for rd in state["rounds"]:
        for value in rd["matches"]:
            if value["id"] == mid:
                return value
    raise p.ProtocolError("unknown match: " + str(mid))


def solution(state, vid):
    return state["solutions"][vid]["artifact"]


def template(state, kind):
    source = p.read_artifact(state, state["instructions_ref"])
    pattern = r"<!-- template:%s -->\s*```text\n(.*?)\n```\s*<!-- /template:%s -->" % (kind, kind)
    found = re.search(pattern, source, re.S)
    if not found:
        raise p.ProtocolError("frozen worker template is missing: " + kind)
    return found.group(1)


def make_job(state, jid, kind, inputs, **metadata):
    if jid in state["jobs"]:
        return state["jobs"][jid]
    context = {key: value for key, value in metadata.items() if key != "snapshot"}
    if kind in ("spawn", "attack", "defend", "candidate"):
        context["strategy_card"] = state["agents"][metadata["agent"]]["card"]
    brief = template(state, kind) + "\n\nRole context:\n" + p.json_text(context)
    if kind == "candidate":
        brief += '\nSearch: python3 "' + str(Path(__file__).with_name("bracket.py"))
        brief += '" pool --dir "' + state["dir"] + '" --job ' + jid + ' --query "concrete need" --limit 5'
    return p.job(state, jid, kind, inputs, brief, **metadata)


def round_snapshot(state, rd):
    if "snapshot" not in rd:
        rd["snapshot"] = {"id": "round-%d" % rd["n"], "ideas": copy.deepcopy(state["ideas"])}
        rd["snapshot_ref"] = p.artifact(state, p.json_text(rd["snapshot"]), "snapshot")
        rd["entries"] = {aid: state["agents"][aid]["solution_version"] for aid in rd["alive"]}
    return rd["snapshot"]


def jobs(state, phase):
    if phase == "spawn":
        inputs = {"baseline": state["baseline_ref"]} if state.get("baseline_ref") else {}
        return [make_job(state, aid + ".spawn", "spawn", inputs, agent=aid, round=0)
                for aid in sorted(state["agents"])]
    if phase == "final":
        fin = state.get("final")
        if not state["champion"] or not fin:
            return []
        refs = {"champion": solution(state, state["agents"][state["champion"]]["solution_version"]),
                "baseline": state["baseline_ref"]}
        return [make_job(state, "final.judge", "final", {"x": refs[fin["X"]], "y": refs[fin["Y"]]},
                         sides=["x", "y"], round=None, match=None)]
    if phase == "recheck":
        return recheck_jobs(state)
    rd = current_round(state)
    if not rd:
        return []
    snapshot = round_snapshot(state, rd)
    result = []
    for m in rd["matches"]:
        a, b, mid = m["a"], m["b"], m["id"]
        if phase in ("attack", "defend", "candidate", "review"):
            for aid, opponent in ((a, b), (b, a)):
                jid = mid + "." + aid + "." + phase
                if jid in state["jobs"]:
                    result.append(state["jobs"][jid])
                    continue
                original = solution(state, rd["entries"][aid])
                inputs = {"preceding": original}
                if phase == "attack":
                    inputs["opponent"] = solution(state, rd["entries"][opponent])
                elif phase == "defend":
                    inputs["attack"] = state["jobs"][mid + "." + opponent + ".attack"]["artifact"]
                elif phase == "candidate":
                    if not any(v["status"] == "active" for v in snapshot["ideas"].values()):
                        continue
                    inputs.update(a0=solution(state, m["a0"][aid]), snapshot=rd["snapshot_ref"])
                else:
                    candidate = state["jobs"].get(mid + "." + aid + ".candidate")
                    if not candidate or not candidate.get("candidate_version"):
                        continue
                    capture = state["captures"][candidate["id"]]
                    inputs.update(a0=solution(state, m["a0"][aid]),
                                  a1=solution(state, candidate["candidate_version"]),
                                  diff=capture["diff"], snapshot=rd["snapshot_ref"])
                    inputs["defense"] = state["jobs"][mid + "." + aid + ".defend"]["defense"]
                result.append(make_job(state, jid, phase, inputs, agent=aid, opponent=opponent,
                                       round=rd["n"], match=mid, snapshot=snapshot["id"]))
        elif phase == "judge":
            inputs = {aid: solution(state, m["accepted"][aid]) for aid in (a, b)}
            for aid in (a, b):
                inputs[aid + "_attack"] = state["jobs"][mid + "." + aid + ".attack"]["artifact"]
                inputs[aid + "_defense"] = state["jobs"][mid + "." + aid + ".defend"]["defense"]
            claims = {aid: state["solutions"][m["accepted"][aid]].get("dependency_removals", []) for aid in (a, b)}
            inputs["dependency_claims"] = p.artifact(state, p.json_text(claims), "claims")
            result.append(make_job(state, mid + ".judge", phase, inputs,
                                   sides=[a, b], match=mid, round=rd["n"]))
        elif phase == "evaluate":
            inputs = {"loser": solution(state, m["accepted"][m["loser"]]), "snapshot": rd["snapshot_ref"]}
            roles = {}
            for aid in (a, b):
                candidate = state["jobs"].get(mid + "." + aid + ".candidate", {})
                candidate_version = candidate.get("candidate_version")
                roles[aid] = {"accepted": solution(state, m["accepted"][aid]),
                              "a0": solution(state, m["a0"][aid]),
                              "candidate": solution(state, candidate_version) if candidate_version else None,
                              "candidate_accepted": candidate_version == m["accepted"][aid]}
                for kind in ("defend", "candidate"):
                    capture = state["captures"].get(mid + "." + aid + "." + kind)
                    if capture:
                        for key in ("before", "after", "diff", "claims"):
                            inputs[aid + "_" + kind + "_" + key] = capture[key]
            inputs["version_roles"] = p.artifact(state, p.json_text(roles), "claims")
            result.append(make_job(state, mid + ".evaluate", phase, inputs, match=mid, round=rd["n"]))
    return result


def next_action(state):
    recovering = [j for j in state["jobs"].values() if j.get("recovery_of") and j["status"] not in TERMINAL]
    if recovering:
        return ("collect" if any(j["status"] == "assigned" and Path(j["outputs"][0]).exists()
                                for j in recovering) else "evaluate"), recovering, recovering
    alerts = jobs(state, "recheck") if state["alerts"] else []
    if alerts:
        left = [j for j in alerts if j["status"] != "completed"]
        if any(j["status"] == "failed" for j in left) or any(j.get("unresolved") for j in alerts):
            return "blocked", left, alerts
        if left:
            return ("collect" if any(Path(j["outputs"][0]).exists() for j in left if j["status"] == "assigned")
                    else "recheck"), left, alerts
    phases = ("spawn", "final") if state["champion"] else ("spawn", "attack", "defend", "candidate", "review", "judge", "evaluate")
    for phase in phases:
        values = jobs(state, phase)
        left = [j for j in values if j["status"] not in TERMINAL]
        if left:
            if any(j["status"] == "failed" for j in left):
                return "blocked", left, values
            if any(Path(j["outputs"][0]).exists() for j in left if j["status"] == "assigned"):
                return "collect", left, values
            return phase, left, values
    return ("done" if state["champion"] else "advance"), [], []


def assign(state, jid, worker):
    if jid not in state["jobs"]:
        raise p.ProtocolError("prepare the current phase before assigning a job")
    value = state["jobs"][jid]
    history = [d for d in state["dispatches"] if d["worker"] == worker]
    if value["kind"] == "candidate":
        defender = state["jobs"][value["match"] + "." + value["agent"] + ".defend"]
        if worker != defender["worker"]:
            raise p.ProtocolError("candidate must continue in its ordinary defender's context")
    if value["kind"] in ("judge", "final"):
        if any(d["kind"] in ("spawn", "attack", "defend", "candidate") for d in history):
            raise p.ProtocolError("a match judge cannot be a competitor worker")
    if value["kind"] == "evaluate":
        judge = state["jobs"][value["match"] + ".judge"]
        if any(d["job"] == judge["id"] for d in history):
            raise p.ProtocolError("idea evaluator must differ from this match's judge")
    if value["kind"] == "review":
        candidate = state["jobs"][value["match"] + "." + value["agent"] + ".candidate"]
        excluded = {candidate["worker"]}
        excluded.update(state["ideas"][iid]["nominator"] for iid in candidate["ideas"])
        if worker in excluded:
            raise p.ProtocolError("addition reviewer cannot be author or nominator")
    if value["kind"] == "recheck":
        excluded = {state["solutions"][value["version"]]["author"],
                    state["ideas"][value["idea"]]["nominator"]}
        if worker in excluded:
            raise p.ProtocolError("rechecker cannot be the solution author or idea nominator")
    return p.assign(state, jid, worker)


def version(state, value, body, before=None, dependencies=None):
    content = text(body["solution"], "solution")
    aid = p.artifact(state, content, "solution")
    vid = "version." + value["id"]
    state["solutions"][vid] = {"artifact": aid, "before": before, "author": value["worker"],
                                "dependencies": list(dependencies or []), "usable": content.strip() != "NO OUTPUT"}
    if before:
        old = solution(state, before)
        diff = "".join(difflib.unified_diff(p.read_artifact(state, old).splitlines(True),
                                           content.splitlines(True), fromfile="before", tofile="after"))
        removed = body.get("removed", [])
        if not isinstance(removed, list):
            raise p.ProtocolError("removed contributions must be an array")
        for claim in removed:
            if not isinstance(claim, dict) or claim.get("source") != old or text(claim.get("passage"), "passage") not in p.read_artifact(state, old):
                raise p.ProtocolError("removed contribution has an invalid source")
            text(claim.get("reason"), "removal reason")
        state["captures"][value["id"]] = {"before": old, "after": aid,
            "diff": p.artifact(state, diff or "No textual changes.", "diff"),
            "claims": p.artifact(state, p.json_text(removed), "claims")}
    return vid


def apply_result(state, value, body):
    kind = value["kind"]
    m = match(state, value["match"]) if value.get("match") else None
    aid = value.get("agent")
    if kind == "spawn":
        vid = version(state, value, body)
        state["agents"][aid].update(solution_version=vid, solution=p.artifact_path(state, solution(state, vid)))
    elif kind == "attack":
        value["artifact"] = p.artifact(state, text(body.get("attack"), "attack"), "attack")
    elif kind == "defend":
        rd = state["rounds"][value["round"] - 1]
        before = rd["entries"][aid]
        vid = version(state, value, body, before, state["solutions"][before]["dependencies"])
        claims = body.get("dependency_removals", [])
        if not isinstance(claims, list):
            raise p.ProtocolError("dependency_removals must be an array")
        for claim in claims:
            if not isinstance(claim, dict) or claim.get("idea") not in state["solutions"][before]["dependencies"]:
                raise p.ProtocolError("invalid dependency removal")
            text(claim.get("reason"), "dependency removal reason")
        state["solutions"][vid]["dependency_removals"] = claims
        value["defense"] = p.artifact(state, text(body.get("defense"), "defense"), "defense")
        m.setdefault("a0", {})[aid] = vid
        m.setdefault("accepted", {})[aid] = vid
    elif kind == "candidate":
        text(body.get("query"), "retrieval query")
        text(body.get("reason"), "fit reason")
        if body.get("decision") != "no_fit":
            apply_candidate(state, value, body)
        else:
            state["adoption_attempts"].append({"job": value["id"], "decision": "no_fit", "reason": body["reason"]})
    elif kind == "review":
        apply_review(state, value, body)
    elif kind in ("judge", "final"):
        from bracket import decide
        if body.get("match") != value.get("match") or set(body.get("scores", {})) != set(value["sides"]):
            raise p.ProtocolError("judge result names the wrong match or scored sides")
        if body.get("winner") not in value["sides"]:
            raise p.ProtocolError("winner must be one exact scored side ID")
        text(body.get("reason"), "judge reason")
        winner, totals, note = decide(body, *value["sides"])
        if not isinstance(body.get("verified_dependency_removals", {}), dict):
            raise p.ProtocolError("verified dependency removals must be an object")
        if kind == "final":
            fin = state["final"]
            champ = "x" if fin["X"] == "champion" else "y"
            state["solutions"][state["agents"][state["champion"]]["solution_version"]]["usable"] &= not body["scores"][champ]["fatal"]
            fin["result"] = {"better": fin[winner.upper()], "champion_total": totals[champ],
                             "baseline_total": totals["y" if champ == "x" else "x"],
                             "reason": body["reason"], "fixed": body.get("fixed", [])}
        else:
            loser = next(side for side in value["sides"] if side != winner)
            m.update(winner=winner, loser=loser, reason=body["reason"], scores=totals,
                     survived=body.get("survived", []), source="judge", note=note)
            for side in value["sides"]:
                current = state["solutions"][m["accepted"][side]]
                current["usable"] = current["usable"] and not body["scores"][side]["fatal"]
                removals = body.get("verified_dependency_removals", {}).get(side, [])
                strings(removals, "verified dependency removals")
                claimed = {c["idea"] for c in current.get("dependency_removals", [])}
                if not set(removals) <= claimed:
                    raise p.ProtocolError("judge verified an unrequested dependency removal")
                current["dependencies"] = [iid for iid in current["dependencies"] if iid not in removals]
                current["verified_dependency_removals"] = removals
    elif kind == "evaluate":
        apply_evaluation(state, value, body)
    elif kind == "recheck":
        apply_recheck(state, value, body)
    value["status"] = "completed"
    value["result"] = body
    value["result_sha256"] = p.digest(p.json_text(body))


def apply_evaluation(state, value, body):
    text(body.get("reason"), "evaluation reason")
    ideas = body.get("ideas")
    if not isinstance(ideas, list):
        raise p.ProtocolError("ideas must be an array, including for an empty evaluation")
    for index, raw in enumerate(ideas):
        if not isinstance(raw, dict):
            raise p.ProtocolError("idea must be an object")
        for field in ("contribution", "benefit", "relevance", "reason"):
            text(raw.get(field), field)
        for field in ("conditions", "dependencies", "limitations", "evidence"):
            strings(raw.get(field), field, nonempty=field in ("conditions", "evidence"))
        source = raw.get("source", {})
        eligible_sources = {ref for name, ref in value["inputs"].items()
                            if name == "loser" or name.endswith("_before")}
        if not isinstance(source, dict) or source.get("artifact") not in eligible_sources:
            raise p.ProtocolError("idea source must be the assigned loser or a captured pre-revision solution")
        passage = text(source.get("passage"), "source passage")
        if passage not in p.read_artifact(state, source["artifact"]):
            raise p.ProtocolError("idea passage does not appear in its source")
        if raw.get("status") not in ("active", "pending"):
            raise p.ProtocolError("new idea status must be active or pending")
        if raw["status"] == "pending":
            text(raw.get("verification_question"), "verification question")
            strings(raw.get("verification_evidence_needed"), "verification evidence needed", True)
        iid = "idea." + value["id"] + ".%d.v1" % (index + 1)
        state["ideas"][iid] = dict(copy.deepcopy(raw), id=iid, version=1, nominator=value["worker"],
                                   source_hash=state["artifacts"][source["artifact"]]["sha256"],
                                   history=[], verification_attempts=[])
    apply_pool_proposals(state, value, body)
    value["outcome"] = "completed_with_ideas" if ideas else "completed_empty"


def collect(state):
    outcomes = []
    for jid in list(state["jobs"]):
        value = state["jobs"][jid]
        if value["status"] != "assigned" or not Path(value["outputs"][0]).is_file():
            continue
        try:
            body = p.read_result(state, value)
            updated = copy.deepcopy(state)
            apply_result(updated, updated["jobs"][jid], body)
            state.clear()
            state.update(updated)
            if state["champion"] and state["jobs"][jid].get("recovery_of"):
                close_round(state)
            outcomes.append((jid, "recorded", state["jobs"][jid].get("outcome", "completed")))
        except (p.ProtocolError, KeyError, TypeError, ValueError) as error:
            fail(state, jid, str(error))
            outcomes.append((jid, "invalid", str(error)))
    return outcomes


def fail(state, jid, reason):
    value = state["jobs"][jid]
    kind = value["kind"]
    limit = 3 if kind in ("judge", "final") else (1 if kind == "candidate" else 2)
    if p.retry(state, jid, text(reason, "failure reason"), limit):
        return
    if kind in ("evaluate", "review", "candidate"):
        value.update(status="deferred", outcome="deferred_after_failure")
        if kind != "evaluate":
            state["adoption_attempts"].append({"job": jid, "decision": "deferred", "reason": reason})
    elif kind in ("spawn", "attack", "defend"):
        body = {"solution": "NO OUTPUT", "attack": "No attack output.", "defense": "NO OUTPUT"}
        apply_result(state, value, body)
        value["outcome"] = "failed_placeholder"


def report(state):
    def incomplete(value):
        recovered = state["jobs"].get(value.get("recovered_by"), {})
        return value["kind"] == "evaluate" and value["status"] == "deferred" and recovered.get("status") != "completed"
    unresolved = []
    for iid, alert in state["alerts"].items():
        fingerprint = p.digest(p.json_text(alert["evidence"]))
        for vid in current_versions(state):
            checked = alert["checks"].get(vid, {})
            if iid in state["solutions"][vid]["dependencies"] and (
                    not checked.get("resolved") or checked.get("fingerprint") != fingerprint):
                unresolved.append({"idea": iid, "version": vid})
    champion = state["agents"].get(state["champion"], {})
    usable = state["solutions"].get(champion.get("solution_version"), {}).get("usable", False)
    pending_final = bool(state.get("final") and not state["final"].get("result"))
    return {"incomplete_preservation": any(incomplete(j) for j in state["jobs"].values()),
            "unresolved_alerts": unresolved, "usable": usable,
            "validated": bool(state["champion"] and usable and not pending_final and not unresolved),
            "validation_scope": "Collected judgments and protocol checks; model correctness is not guaranteed.",
            "dispatches": len(state["dispatches"]),
            "retries": sum(d["attempt"] > 1 for d in state["dispatches"]),
            "candidate_continuations": sum(d["kind"] == "candidate" for d in state["dispatches"]),
            "exceptional_rechecks": sum(d["kind"] == "recheck" for d in state["dispatches"]),
            "worker_reuse": sorted({d["worker"] for d in state["dispatches"]
                                    if sum(e["worker"] == d["worker"] for e in state["dispatches"]) > 1}),
            "ideas": {status: sum(i["status"] == status for i in state["ideas"].values())
                      for status in ("active", "pending", "retired")}}


def defer(state, jid, reason):
    value = state["jobs"].get(jid)
    if not value or value["kind"] not in ("candidate", "review", "evaluate") or value["status"] != "unassigned":
        raise p.ProtocolError("only an unassigned optional job can be deferred for unavailable workers")
    if reason != "no_eligible_worker":
        raise p.ProtocolError("administrative deferral requires reason no_eligible_worker")
    value.update(status="deferred", outcome="deferred_after_failure", error=reason)
    if value["kind"] in ("review", "candidate"):
        state["adoption_attempts"].append({"job": jid, "decision": "deferred", "reason": reason})


def recover(state, jid):
    value = state["jobs"].get(jid)
    if not value or value["kind"] != "evaluate" or value["status"] != "deferred":
        raise p.ProtocolError("recovery requires a deferred evaluation")
    if value.get("recovered_by"):
        return state["jobs"][value["recovered_by"]]
    recovered = p.job(state, jid + ".recovery", "evaluate", value["inputs"], value["brief"],
                      match=value["match"], round=value["round"], recovery_of=jid)
    value["recovered_by"] = recovered["id"]
    return recovered


def apply_pool_proposals(state, value, body):
    retirements, updates = body.get("retirements", []), body.get("updates", [])
    if not isinstance(retirements, list) or not isinstance(updates, list):
        raise p.ProtocolError("retirements and updates must be arrays")
    snapshot = p.parse_json(p.read_artifact(state, value["inputs"]["snapshot"]))["ideas"]
    for proposal in retirements:
        if not isinstance(proposal, dict) or proposal.get("idea") not in snapshot:
            raise p.ProtocolError("retirement must name an assigned idea version")
        strings(proposal.get("evidence"), "retirement evidence", True)
        reason = proposal.get("reason")
        if reason not in ("disproven", "duplicate", "superseded"):
            raise p.ProtocolError("unsupported retirement reason")
        replacement = proposal.get("replacement")
        if replacement is not None and not isinstance(replacement, str):
            raise p.ProtocolError("replacement must be an idea ID or null")
        if reason != "disproven":
            available = dict(snapshot)
            available.update({iid: item for iid, item in state["ideas"].items()
                              if iid.startswith("idea." + value["id"] + ".")})
            if replacement == proposal["idea"] or available.get(replacement, {}).get("status") != "active":
                raise p.ProtocolError("retirement needs a distinct active assigned replacement")
        else:
            alert = state["alerts"].setdefault(proposal["idea"], {
                "idea": proposal["idea"], "evidence": [], "source_jobs": [], "checks": {}})
            alert["evidence"] = sorted(set(alert["evidence"] + proposal["evidence"]))
            alert["source_jobs"] = sorted(set(alert["source_jobs"] + [value["id"]]))
    for proposal in updates:
        if not isinstance(proposal, dict) or snapshot.get(proposal.get("idea"), {}).get("status") != "pending":
            raise p.ProtocolError("verification update needs an assigned pending idea")
        if proposal.get("status") not in ("active", "pending"):
            raise p.ProtocolError("verification outcome must be active or pending")
        strings(proposal.get("evidence"), "new verification evidence", True)
        text(proposal.get("reason"), "verification reason")
        text(proposal.get("change"), "material evidence or conditions changed")
        idea = state["ideas"][proposal["idea"]]
        fingerprint = p.digest(p.json_text({"question": idea["verification_question"],
            "evidence": sorted({e.strip().casefold() for e in proposal["evidence"]}),
            "change": proposal["change"].strip().casefold()}))
        if any(a["fingerprint"] == fingerprint for a in idea["verification_attempts"]):
            raise p.ProtocolError("verification already attempted with the same evidence and conditions")
        idea["verification_attempts"].append(dict(copy.deepcopy(proposal), fingerprint=fingerprint,
                                                  job=value["id"]))
    value["pool_proposals"] = {"retirements": copy.deepcopy(retirements), "updates": copy.deepcopy(updates)}


def close_round(state):
    """Commit ordinary pool decisions together, independent of completion order."""
    pending = [j for j in state["jobs"].values() if j["kind"] == "evaluate"
               and j["status"] == "completed" and not j.get("pool_committed")]
    by_idea = {}
    for value in sorted(pending, key=lambda item: item["id"]):
        proposals = value.get("pool_proposals", {})
        for action in ("retirements", "updates"):
            for proposal in proposals.get(action, []):
                by_idea.setdefault(proposal["idea"], []).append((action, proposal, value["id"]))
    for iid, proposals in sorted(by_idea.items()):
        idea = state["ideas"][iid]
        signatures = {(kind, item.get("reason") if kind == "retirements" else item["status"],
                       item.get("replacement")) for kind, item, _ in proposals}
        if len(signatures) != 1:
            idea["history"].append({"decision": "conflicting_proposals", "proposals": proposals})
            continue
        action, proposal, _ = proposals[0]
        if action == "retirements":
            replacement = proposal.get("replacement")
            if proposal["reason"] != "disproven" and (
                    replacement in by_idea or state["ideas"].get(replacement, {}).get("status") != "active"):
                idea["history"].append({"decision": "replacement_unresolved", "proposals": proposals})
                continue
            idea.update(status="retired", retirement=copy.deepcopy(proposal))
        elif idea["status"] == "pending":
            idea["status"] = proposal["status"]
        idea["history"].append({"decision": action, "proposals": proposals})
    for value in pending:
        value["pool_committed"] = True


def apply_candidate(state, value, body):
    if body.get("decision") != "candidate":
        raise p.ProtocolError("candidate decision must be candidate or no_fit")
    selected = strings(body.get("ideas"), "selected ideas", True)
    if len(selected) != len(set(selected)):
        raise p.ProtocolError("duplicate selected idea versions")
    snapshot = p.parse_json(p.read_artifact(state, value["inputs"]["snapshot"]))
    for iid in selected:
        if snapshot["ideas"].get(iid, {}).get("status") != "active" or blocked_idea(state, iid):
            raise p.ProtocolError("candidate uses an unavailable or blocked idea version")
    m = match(state, value["match"])
    original = m["a0"][value["agent"]]
    dependencies = sorted(set(state["solutions"][original]["dependencies"] + selected))
    vid = version(state, value, body, original, dependencies)
    state["solutions"][vid]["dependency_removals"] = copy.deepcopy(
        state["solutions"][original].get("dependency_removals", []))
    value.update(candidate_version=vid, ideas=list(selected))
    state["adoption_attempts"].append({"job": value["id"], "decision": "awaiting_review",
        "a0": original, "a1": vid, "ideas": selected, "reason": body["reason"]})


def apply_review(state, value, body):
    positive = ("a1_usable", "scope_preserved", "constraints_preserved", "meaningful_improvement")
    for key in positive + ("baseline_sound", "a0_usable", "important_regression"):
        if type(body.get(key)) is not bool:
            raise p.ProtocolError(key + " must be a boolean")
    for key in ("reason", "benefit"):
        text(body.get(key), key)
    for key in ("constraints", "evidence", "limitations"):
        strings(body.get(key), key, nonempty=key != "limitations")
    if body.get("decision") not in ("accept", "reject"):
        raise p.ProtocolError("review decision must be accept or reject")
    if body["decision"] == "accept" and (not all(body[key] for key in positive) or body["important_regression"]):
        raise p.ProtocolError("acceptance contradicts a required guard")
    if body["baseline_sound"] != body["a0_usable"]:
        raise p.ProtocolError("baseline_sound must agree with a0_usable")
    if body["decision"] == "accept" and not body["a0_usable"]:
        text(body.get("repair_evidence"), "verified A0 repair evidence")
    candidate = state["jobs"][value["match"] + "." + value["agent"] + ".candidate"]
    if body["decision"] == "accept" and any(blocked_idea(state, iid) for iid in candidate["ideas"]):
        raise p.ProtocolError("candidate depends on a blocked idea")
    m = match(state, value["match"])
    a0 = m["a0"][value["agent"]]
    state["solutions"][a0]["usable"] = state["solutions"][a0]["usable"] and body["a0_usable"]
    accepted = candidate["candidate_version"] if body["decision"] == "accept" else a0
    m["accepted"][value["agent"]] = accepted
    for attempt in state["adoption_attempts"]:
        if attempt["job"] == candidate["id"]:
            attempt.update(decision=body["decision"], review_job=value["id"], reviewer=value["worker"],
                           accepted=accepted, evidence=body["evidence"], reason=body["reason"])


def blocked_idea(state, iid):
    return any(alert["idea"] == iid for alert in state["alerts"].values())


def retrieve(state, jid, query, limit=5):
    value = state["jobs"].get(jid)
    if not value or value["kind"] != "candidate":
        raise p.ProtocolError("retrieval needs a prepared candidate job and its fixed snapshot")
    if type(limit) is not int or not 1 <= limit <= 10:
        raise p.ProtocolError("shortlist limit must be between 1 and 10; storage is not capped")
    terms = set(re.findall(r"\w+", text(query, "query").casefold()))
    if not terms:
        raise p.ProtocolError("query needs a concrete searchable requirement")
    snapshot = p.parse_json(p.read_artifact(state, value["inputs"]["snapshot"]))
    ranked = []
    for iid, idea in snapshot["ideas"].items():
        if idea["status"] != "active" or blocked_idea(state, iid):
            continue
        searchable = " ".join([idea["contribution"], idea["benefit"], idea["relevance"]]
                              + idea["conditions"] + idea["dependencies"] + idea["limitations"])
        score = len(terms & set(re.findall(r"\w+", searchable.casefold())))
        if score:
            ranked.append((score, iid, idea))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    return {"snapshot": snapshot["id"], "query": query, "ideas": [copy.deepcopy(item[2]) for item in ranked[:limit]],
            "matching_count": len(ranked), "truncated": len(ranked) > limit,
            "limits": "Lexical shortlist only. Inspect conditions and use a focused follow-up when warranted; absent results are not rejection."}


def current_versions(state):
    versions = {}
    rd = current_round(state)
    for aid, agent in state["agents"].items():
        if not agent["alive"] or not agent.get("solution_version"):
            continue
        vid = agent["solution_version"]
        if rd:
            for m in rd["matches"]:
                if aid in (m["a"], m["b"]):
                    if m["winner"] and m["winner"] != aid:
                        vid = None
                    else:
                        vid = m.get("accepted", {}).get(aid, vid)
        if vid:
            versions[vid] = aid
    return versions


def recheck_jobs(state):
    versions = current_versions(state)
    rd = current_round(state)
    result = []
    for iid, alert in sorted(state["alerts"].items()):
        fingerprint = p.digest(p.json_text(alert["evidence"]))
        for vid, aid in versions.items():
            if iid not in state["solutions"][vid]["dependencies"]:
                continue
            checked = alert["checks"].get(vid)
            if checked and checked["fingerprint"] == fingerprint and checked["resolved"]:
                continue
            jid = "recheck." + p.digest(iid + vid + fingerprint)[:24]
            inputs = {"solution": solution(state, vid),
                      "idea": p.artifact(state, p.json_text(state["ideas"][iid]), "idea"),
                      "evidence": p.artifact(state, p.json_text(alert["evidence"]), "evidence")}
            result.append(make_job(state, jid, "recheck", inputs, agent=aid, version=vid,
                                   idea=iid, fingerprint=fingerprint, round=rd["n"] if rd else None))
    return result


def apply_recheck(state, value, body):
    if value["fingerprint"] != p.digest(p.json_text(state["alerts"][value["idea"]]["evidence"])):
        raise p.ProtocolError("recheck evidence changed; this result is stale")
    for key in ("resolved", "dependency_removed"):
        if type(body.get(key)) is not bool:
            raise p.ProtocolError(key + " must be a boolean")
    strings(body.get("evidence"), "recheck evidence", True)
    text(body.get("reason"), "recheck reason")
    if body["dependency_removed"] and not body["resolved"]:
        raise p.ProtocolError("unresolved recheck cannot clear a dependency")
    alert = state["alerts"][value["idea"]]
    alert["checks"][value["version"]] = dict(copy.deepcopy(body), fingerprint=value["fingerprint"], job=value["id"])
    value["unresolved"] = not body["resolved"]
    if body["dependency_removed"]:
        current = state["solutions"][value["version"]]
        current["dependencies"] = [iid for iid in current["dependencies"] if iid != value["idea"]]
        current.setdefault("dependency_history", []).append({"removed": value["idea"], "recheck": value["id"],
                                                              "reason": body["reason"]})
