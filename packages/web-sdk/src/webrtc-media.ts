/** Browser SmallWebRTC signaling (media plane) — no adapter imports. */

export type VoiceConnectionState = "disconnected" | "connecting" | "connected" | "failed";

export type SmallWebRtcConnectOptions = {
  gatewayUrl: string;
  sessionId: string;
  devToken: string;
  iceServers?: RTCIceServer[];
};

export type SmallWebRtcSession = {
  connectionState: VoiceConnectionState;
  connect: () => Promise<void>;
  disconnect: () => Promise<void>;
  setMicMuted: (muted: boolean) => void;
  onConnectionState: (handler: (state: VoiceConnectionState) => void) => () => void;
  /** 0–1 mic level when connected (optional). */
  onAudioLevel: (handler: (level: number) => void) => () => void;
};

type IcePayload = {
  candidate: string;
  sdp_mid: string;
  sdp_mline_index: number;
};

export function attachSmallWebRtcMedia(options: SmallWebRtcConnectOptions): SmallWebRtcSession {
  const baseUrl = options.gatewayUrl.replace(/\/$/, "");
  const offerUrl = `${baseUrl}/sessions/${encodeURIComponent(options.sessionId)}/webrtc/offer?token=${encodeURIComponent(options.devToken)}`;

  let connectionState: VoiceConnectionState = "disconnected";
  let pc: RTCPeerConnection | null = null;
  let pcId: string | null = null;
  let localStream: MediaStream | null = null;
  let remoteAudio: HTMLAudioElement | null = null;
  let analyser: AnalyserNode | null = null;
  let audioContext: AudioContext | null = null;
  let levelTimer: ReturnType<typeof setInterval> | null = null;
  let canSendIce = false;
  const iceQueue: RTCIceCandidate[] = [];
  const stateHandlers = new Set<(state: VoiceConnectionState) => void>();
  const levelHandlers = new Set<(level: number) => void>();

  const setState = (next: VoiceConnectionState) => {
    connectionState = next;
    for (const handler of stateHandlers) handler(next);
  };

  const onConnectionState = (handler: (state: VoiceConnectionState) => void) => {
    stateHandlers.add(handler);
    handler(connectionState);
    return () => stateHandlers.delete(handler);
  };

  const onAudioLevel = (handler: (level: number) => void) => {
    levelHandlers.add(handler);
    return () => levelHandlers.delete(handler);
  };

  const flushIce = async () => {
    if (!pcId || !canSendIce || iceQueue.length === 0) return;
    const candidates: IcePayload[] = iceQueue.splice(0, iceQueue.length).map((c) => ({
      candidate: c.candidate ?? "",
      sdp_mid: c.sdpMid ?? "",
      sdp_mline_index: c.sdpMLineIndex ?? 0,
    }));
    await fetch(offerUrl, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pc_id: pcId, candidates }),
    });
  };

  const sendIce = async (candidate: RTCIceCandidate | null) => {
    if (!candidate) return;
    if (!canSendIce || !pcId) {
      iceQueue.push(candidate);
      return;
    }
    await fetch(offerUrl, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        pc_id: pcId,
        candidates: [
          {
            candidate: candidate.candidate ?? "",
            sdp_mid: candidate.sdpMid ?? "",
            sdp_mline_index: candidate.sdpMLineIndex ?? 0,
          },
        ],
      }),
    });
  };

  const startLevelMeter = (stream: MediaStream) => {
    audioContext = new AudioContext();
    const source = audioContext.createMediaStreamSource(stream);
    analyser = audioContext.createAnalyser();
    analyser.fftSize = 256;
    source.connect(analyser);
    const data = new Uint8Array(analyser.frequencyBinCount);
    levelTimer = setInterval(() => {
      if (!analyser) return;
      analyser.getByteFrequencyData(data);
      let sum = 0;
      for (const v of data) sum += v;
      const level = sum / (data.length * 255);
      for (const handler of levelHandlers) handler(level);
    }, 100);
  };

  const stopLevelMeter = () => {
    if (levelTimer) clearInterval(levelTimer);
    levelTimer = null;
    analyser = null;
    void audioContext?.close();
    audioContext = null;
  };

  const playRemoteTrack = async (track: MediaStreamTrack) => {
    const stream = new MediaStream([track]);
    if (!remoteAudio) {
      remoteAudio = document.createElement("audio");
      remoteAudio.autoplay = true;
      remoteAudio.playsInline = true;
      remoteAudio.setAttribute("playsinline", "true");
      document.body.appendChild(remoteAudio);
    }
    remoteAudio.muted = false;
    remoteAudio.srcObject = stream;

    try {
      await remoteAudio.play();
    } catch (err) {
      console.warn("relay webrtc: remote audio element play failed", err);
    }
  };

  const connect = async () => {
    if (connectionState === "connecting" || connectionState === "connected") return;
    setState("connecting");
    canSendIce = false;
    pcId = null;
    iceQueue.length = 0;

    try {
      localStream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
      startLevelMeter(localStream);
      if (audioContext?.state === "suspended") {
        await audioContext.resume();
      }

      pc = new RTCPeerConnection({
        iceServers: options.iceServers ?? [{ urls: "stun:stun.l.google.com:19302" }],
      });
      for (const track of localStream.getAudioTracks()) {
        pc.addTransceiver(track, { direction: "sendrecv", streams: [localStream] });
      }

      pc.onicecandidate = (event) => {
        void sendIce(event.candidate);
      };

      pc.ontrack = (event) => {
        if (event.track.kind !== "audio") return;
        void playRemoteTrack(event.track);
      };

      pc.oniceconnectionstatechange = () => {
        if (!pc) return;
        if (pc.iceConnectionState === "connected" || pc.iceConnectionState === "completed") {
          setState("connected");
        } else if (pc.iceConnectionState === "failed") {
          setState("failed");
        }
      };

      const offer = await pc.createOffer();
      await pc.setLocalDescription(offer);

      const resp = await fetch(offerUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          sdp: pc.localDescription?.sdp,
          type: pc.localDescription?.type,
          pc_id: pcId,
        }),
      });
      if (!resp.ok) {
        throw new Error(`webrtc offer failed: ${resp.status}`);
      }
      const answer = (await resp.json()) as { sdp: string; type: RTCSdpType; pc_id: string };
      pcId = answer.pc_id;
      await pc.setRemoteDescription(answer);
      canSendIce = true;
      await flushIce();
      if (pc.iceConnectionState === "connected" || pc.iceConnectionState === "completed") {
        setState("connected");
      }
    } catch (e) {
      setState("failed");
      await disconnect();
      throw e;
    }
  };

  const disconnect = async () => {
    canSendIce = false;
    stopLevelMeter();
    localStream?.getTracks().forEach((t) => t.stop());
    localStream = null;
    if (pc) {
      pc.onicecandidate = null;
      pc.close();
    }
    pc = null;
    pcId = null;
    if (remoteAudio) {
      remoteAudio.srcObject = null;
      remoteAudio.remove();
      remoteAudio = null;
    }
    setState("disconnected");
  };

  const setMicMuted = (muted: boolean) => {
    if (!localStream) return;
    for (const track of localStream.getAudioTracks()) {
      track.enabled = !muted;
    }
  };

  return {
    get connectionState() {
      return connectionState;
    },
    connect,
    disconnect,
    setMicMuted,
    onConnectionState,
    onAudioLevel,
  };
}
