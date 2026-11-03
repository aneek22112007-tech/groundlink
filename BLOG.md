# The audit trail is the product

GroundLink is a mission room for a commercial satellite that has stopped answering the ground. The operators already have a team chat. The agents come to that chat. They do not get a button that fires a thruster.

## The room

Switch carries the messages. Mattermost, from the Switch collab profile, is where Priya and Arjun type. Three Python agents subscribe with server-sent events and post back over HTTP. That is the agent protocol this project implements: SSE in, HTTP out, a beat every two seconds.

The context agent writes one screen when the downlink drops: what is wrong, when it started, what still works, and the countdown to Bengaluru. The options agent always posts three options. The figures come from stepping the same power, attitude, fuel, and thermal functions the simulator uses. The model, if a key is configured, may only rephrase. With no key the deterministic paragraph is what the room sees, so a demo does not depend on a provider.

Option A is a magnetorquer desaturation. It is reversible and slow. Option B is a reaction-control burn on pass 3. It spends propellant, so it is irreversible. Option C sheds the payload and sun-points. It is reversible and the service goes away.

## The gate

Priya can reject A as too slow and ask for a fuel-saving variant. That request is not an approval. The options agent bumps the version and posts the new three.

Arjun authorises B by typing the command-responsibility statement while the pass is open. Priya confirms, as a second person. Only then does `commit_transmit` move the queued steps to `transmitted`. An observer saying the same words is refused in the thread. A message after loss of signal is refused. An approval that names an older version is refused.

The property test is the one that matters: no command reaches `transmitted` without a valid approval row.

## The kill-switch

Run the same anomaly with persistence off. The agents do not read the room memory, so they diagnose twice, queue two command sequences, and never see an authorisation that lived only in the chat. The gate still holds. The bus voltage crosses the survival floor. The dashboard says lost. `logs/comparison.md` puts the two transcripts next to each other.

## The link

Every mission event stores the hash of the previous row plus its own canonical JSON. The audit page is one URL. It names the approver, the role, the statement, and the message id. The PDF is that page in a form you can hand to someone who will not open the dashboard.

## What I would not claim

This is not a flight computer. The orbit model is circular and Keplerian so the pass window is reproducible, not so it can task a real spacecraft. The July incidents are fixture rows that make the context sentence true at the demo epoch. There is no published demo video; the landing page plays the room log from a real playback of this code.

The landing page is a separate static site: a Three.js Earth, a satellite built from boxes and a cylinder, and a scroll story. Day and night textures are NASA public-domain imagery via the three-globe example set. Clouds are drawn in the page.

Switch is the centre of the room. The agents do not talk to each other through a side channel. They talk where the humans can read them, and the humans are the ones who sign.
