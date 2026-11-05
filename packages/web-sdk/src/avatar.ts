// Optional assistant avatar. Import from "@sumukhj1219-wkt-org/relay-web-sdk/avatar"; apps that don't use it
// don't bundle it. Two layers:
//   watchAssistantState: renderer-free state (idle / listening / thinking / speaking) from session events,
//                        for apps that draw their own avatar (React, canvas, sprites, …).
//   mountAvatar:         a ready-made video avatar: loops a "talking" clip while the assistant speaks and
//                        crossfades to an idle clip (or a still image) otherwise.

export type AssistantState = "idle" | "listening" | "thinking" | "speaking";

/** The part of a Relay session the avatar needs (any `createRelaySession` result fits). */
export type AvatarSession = {
  on: (eventType: string, handler: (event: { type: string; payload?: Record<string, unknown> }) => void) => () => void;
};

export type AssistantStateOptions = {
  /** Keep "speaking" this long after speech stops, so short pauses between sentences don't flicker. Default 350 ms. */
  speakingHoldMs?: number;
  /**
   * Text sessions have no speech events: treat streaming reply text as speaking (until `textHoldMs` after the
   * last chunk). Ignored once the session has spoken with voice. Default true.
   */
  textSpeaking?: boolean;
  /** Default 700 ms. */
  textHoldMs?: number;
};

type Timers = {
  setTimeout: (fn: () => void, ms: number) => unknown;
  clearTimeout: (handle: unknown) => void;
};

const defaultTimers: Timers = {
  setTimeout: (fn, ms) => setTimeout(fn, ms),
  clearTimeout: (handle) => clearTimeout(handle as ReturnType<typeof setTimeout>),
};

/**
 * Calls `onChange` with the assistant's state now and on every change. Priority: speaking > listening >
 * thinking > idle. Returns a function that stops watching.
 */
export function watchAssistantState(
  session: AvatarSession,
  onChange: (state: AssistantState) => void,
  options: AssistantStateOptions = {},
  timers: Timers = defaultTimers,
): () => void {
  const speakingHoldMs = options.speakingHoldMs ?? 350;
  const textHoldMs = options.textHoldMs ?? 700;
  const textSpeaking = options.textSpeaking ?? true;

  let speaking = false;
  let listening = false;
  let thinking = false;
  let voiceSeen = false;
  let current: AssistantState | null = null;
  let stopTimer: unknown = null;

  const publish = () => {
    const next: AssistantState = speaking ? "speaking" : listening ? "listening" : thinking ? "thinking" : "idle";
    if (next === current) return;
    current = next;
    try {
      onChange(next);
    } catch (err) {
      console.error("relay avatar: onChange threw", err);
    }
  };

  const cancelStop = () => {
    if (stopTimer !== null) timers.clearTimeout(stopTimer);
    stopTimer = null;
  };

  const startSpeaking = () => {
    cancelStop();
    speaking = true;
    publish();
  };

  const stopSpeaking = (afterMs: number) => {
    cancelStop();
    if (afterMs <= 0) {
      speaking = false;
      publish();
      return;
    }
    stopTimer = timers.setTimeout(() => {
      stopTimer = null;
      speaking = false;
      publish();
    }, afterMs);
  };

  const handlers: Record<string, () => void> = {
    SPEECH_STARTED: () => {
      voiceSeen = true;
      startSpeaking();
    },
    SPEECH_STOPPED: () => stopSpeaking(speakingHoldMs),
    INTERRUPTION_DETECTED: () => stopSpeaking(0),
    RESPONSE_INTERRUPTED: () => stopSpeaking(0),
    RESPONSE_DELTA: () => {
      if (!textSpeaking || voiceSeen) return;
      startSpeaking();
      stopSpeaking(textHoldMs);
    },
    USER_SPEECH_STARTED: () => {
      listening = true;
      publish();
    },
    USER_SPEECH_ENDED: () => {
      listening = false;
      publish();
    },
    TURN_STARTED: () => {
      thinking = true;
      publish();
    },
    TURN_PROCESSING: () => {
      thinking = true;
      listening = false;
      publish();
    },
    TURN_COMPLETED: () => {
      thinking = false;
      listening = false;
      publish();
    },
    SESSION_ENDED: () => {
      thinking = false;
      listening = false;
      stopSpeaking(0);
    },
  };

  const unsubscribe = Object.entries(handlers).map(([type, handler]) => session.on(type, handler));
  publish();
  return () => {
    cancelStop();
    for (const off of unsubscribe) off();
  };
}

export type AvatarOptions = AssistantStateOptions & {
  /** Video looped while the assistant speaks (muted; the voice comes from the session). Required. */
  talking: string;
  /** Video looped while idle. Without it the `poster` image is shown. */
  idle?: string;
  /** Optional clips for these states; each falls back to `idle`. */
  listening?: string;
  thinking?: string;
  /** Still image shown while videos load, and as the idle picture when there is no `idle` clip. Recommended. */
  poster?: string;
  /** Accessible description of the avatar. Default "Assistant". */
  label?: string;
  /** How media fills the container. Default "cover". */
  fit?: "cover" | "contain";
  /** Crossfade duration. Default 200 ms. */
  fadeMs?: number;
  /**
   * `[minMs, maxMs]`: while idle, listening or thinking, show the `poster` and play the idle clip once at
   * random intervals in this range (e.g. a blink or a glance), instead of looping it. Needs `poster`; the
   * clip should start and end on the poster's frame. Without it the idle clip loops.
   */
  idleInterval?: [number, number];
  onStateChange?: (state: AssistantState) => void;
};

export type AvatarHandle = {
  /** The state currently shown. */
  readonly state: AssistantState;
  /** Stop listening to the session and remove the avatar's elements. */
  destroy: () => void;
};

/**
 * Renders a video avatar into `container` (give it a size; the media fills it). The container gets
 * `data-relay-avatar-state="idle|listening|thinking|speaking"` for styling (e.g. a ring while thinking).
 */
export function mountAvatar(container: HTMLElement, session: AvatarSession, options: AvatarOptions): AvatarHandle {
  if (!options || !options.talking) throw new Error("mountAvatar: options.talking (a video URL) is required");
  const doc = container.ownerDocument;
  const fadeMs = options.fadeMs ?? 200;
  const fit = options.fit ?? "cover";

  const root = doc.createElement("div");
  root.setAttribute("role", "img");
  root.setAttribute("aria-label", options.label ?? "Assistant");
  root.style.cssText = "position:relative;width:100%;height:100%;overflow:hidden";

  const interval = options.idleInterval;
  if (interval && !(interval.length === 2 && interval[0] >= 0 && interval[1] >= interval[0])) {
    throw new Error("mountAvatar: idleInterval must be [minMs, maxMs] with 0 <= minMs <= maxMs");
  }
  const idleInterval = interval && options.poster ? interval : null;
  // Clips played once now and then over the poster, rather than looped.
  const occasional = (src: string) => idleInterval !== null && src !== options.talking;

  const layerStyle = `position:absolute;inset:0;width:100%;height:100%;object-fit:${fit};transition:opacity ${fadeMs}ms ease;`;

  if (options.poster) {
    const img = doc.createElement("img");
    img.src = options.poster;
    img.alt = "";
    img.style.cssText = layerStyle + "opacity:1";
    root.appendChild(img);
  }

  // One <video> per distinct clip; states share a layer when they use the same clip.
  const layers = new Map<string, HTMLVideoElement>();
  const clipFor = (state: AssistantState): string | null => {
    if (state === "speaking") return options.talking;
    if (state === "listening") return options.listening ?? options.idle ?? null;
    if (state === "thinking") return options.thinking ?? options.idle ?? null;
    return options.idle ?? null;
  };
  for (const state of ["idle", "listening", "thinking", "speaking"] as const) {
    const src = clipFor(state);
    if (!src || layers.has(src)) continue;
    const video = doc.createElement("video");
    video.src = src;
    video.muted = true;
    video.loop = !occasional(src);
    video.playsInline = true;
    video.preload = "auto";
    video.setAttribute("muted", "");
    video.setAttribute("playsinline", "");
    video.setAttribute("aria-hidden", "true");
    video.style.cssText = layerStyle + "opacity:0";
    root.appendChild(video);
    layers.set(src, video);
  }
  container.appendChild(root);

  let state: AssistantState = "idle";
  let shown: HTMLVideoElement | null = null;
  const pauseTimers = new Map<HTMLVideoElement, ReturnType<typeof setTimeout>>();
  let idleTimer: ReturnType<typeof setTimeout> | null = null;

  const clearIdle = () => {
    if (idleTimer !== null) clearTimeout(idleTimer);
    idleTimer = null;
  };
  const playFromStart = (video: HTMLVideoElement) => {
    video.currentTime = 0;
    video.style.opacity = "1";
    const playing = video.play();
    if (playing && typeof playing.catch === "function") playing.catch(() => {});
  };
  // Poster now; the clip once after a random wait; back to the poster when it ends; repeat.
  const scheduleIdle = (video: HTMLVideoElement) => {
    clearIdle();
    if (!idleInterval) return;
    const [min, max] = idleInterval;
    idleTimer = setTimeout(() => {
      idleTimer = null;
      if (shown === video) playFromStart(video);
    }, min + Math.random() * (max - min));
  };
  for (const [src, video] of layers) {
    if (!occasional(src)) continue;
    video.onended = () => {
      video.style.opacity = "0";
      if (shown === video) scheduleIdle(video);
    };
  }

  const show = (next: AssistantState) => {
    state = next;
    container.setAttribute("data-relay-avatar-state", next);
    const src = clipFor(next);
    const video = src ? layers.get(src) ?? null : null;
    if (video !== shown) {
      clearIdle();
      const previous = shown;
      if (video && src && occasional(src)) {
        const pending = pauseTimers.get(video);
        if (pending) clearTimeout(pending);
        pauseTimers.delete(video);
        video.pause();
        video.style.opacity = "0"; // the poster shows until the next random play
      } else if (video) {
        const pending = pauseTimers.get(video);
        if (pending) clearTimeout(pending);
        pauseTimers.delete(video);
        video.style.opacity = "1";
        // Resumes where it paused, so the motion continues instead of restarting. Muted autoplay is allowed.
        const playing = video.play();
        if (playing && typeof playing.catch === "function") playing.catch(() => {});
      }
      if (previous) {
        previous.style.opacity = "0";
        // Pause after the fade so hidden clips don't decode in the background.
        pauseTimers.set(previous, setTimeout(() => {
          pauseTimers.delete(previous);
          previous.pause();
        }, fadeMs));
      }
      shown = video;
      if (video && src && occasional(src)) scheduleIdle(video);
    }
    options.onStateChange?.(next);
  };

  const stop = watchAssistantState(session, show, options);
  return {
    get state() {
      return state;
    },
    destroy() {
      stop();
      clearIdle();
      for (const timer of pauseTimers.values()) clearTimeout(timer);
      for (const video of layers.values()) {
        video.pause();
        video.removeAttribute("src");
      }
      root.remove();
      container.removeAttribute("data-relay-avatar-state");
    },
  };
}
