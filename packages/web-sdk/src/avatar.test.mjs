import test from "node:test";
import assert from "node:assert/strict";
import { mountAvatar, watchAssistantState } from "../dist/avatar.js";

function fakeSession() {
  const handlers = new Map();
  return {
    on(type, handler) {
      if (!handlers.has(type)) handlers.set(type, new Set());
      handlers.get(type).add(handler);
      return () => handlers.get(type).delete(handler);
    },
    emit(type) {
      for (const handler of handlers.get(type) ?? []) handler({ type, payload: {} });
    },
    count: () => [...handlers.values()].reduce((n, set) => n + set.size, 0),
  };
}

function fakeTimers() {
  let pending = [];
  return {
    setTimeout(fn, ms) {
      const t = { fn, ms };
      pending.push(t);
      return t;
    },
    clearTimeout(t) {
      pending = pending.filter((p) => p !== t);
    },
    flush() {
      const run = pending;
      pending = [];
      for (const t of run) t.fn();
    },
  };
}

test("voice session: thinking, speaking with a hold over short pauses, then idle", () => {
  const session = fakeSession();
  const timers = fakeTimers();
  const seen = [];
  const stop = watchAssistantState(session, (s) => seen.push(s), {}, timers);
  session.emit("USER_SPEECH_STARTED");
  session.emit("USER_SPEECH_ENDED");
  session.emit("TURN_STARTED");
  session.emit("SPEECH_STARTED");
  session.emit("SPEECH_STOPPED");
  session.emit("SPEECH_STARTED"); // next sentence within the hold: no flicker
  session.emit("SPEECH_STOPPED");
  timers.flush();
  session.emit("TURN_COMPLETED");
  assert.deepEqual(seen, ["idle", "listening", "idle", "thinking", "speaking", "thinking", "idle"]);

  // Once voice has been heard, streaming text no longer counts as speaking.
  session.emit("RESPONSE_DELTA");
  assert.equal(seen.at(-1), "idle");

  // Interruptions stop speaking at once.
  session.emit("SPEECH_STARTED");
  session.emit("INTERRUPTION_DETECTED");
  assert.deepEqual(seen.slice(-2), ["speaking", "idle"]);

  stop();
  assert.equal(session.count(), 0);
});

test("text session: streaming reply text animates the avatar unless disabled", () => {
  const session = fakeSession();
  const timers = fakeTimers();
  const seen = [];
  watchAssistantState(session, (s) => seen.push(s), {}, timers);
  session.emit("TURN_STARTED");
  session.emit("RESPONSE_DELTA");
  session.emit("RESPONSE_DELTA");
  timers.flush();
  session.emit("TURN_COMPLETED");
  assert.deepEqual(seen, ["idle", "thinking", "speaking", "thinking", "idle"]);

  const quiet = fakeSession();
  const states = [];
  watchAssistantState(quiet, (s) => states.push(s), { textSpeaking: false }, fakeTimers());
  quiet.emit("RESPONSE_DELTA");
  assert.deepEqual(states, ["idle"]);
});

function fakeDocument() {
  const make = (tag) => {
    const el = {
      tagName: tag.toUpperCase(),
      style: {},
      attrs: {},
      children: [],
      parent: null,
      plays: 0,
      paused: true,
      setAttribute(name, value) {
        this.attrs[name] = String(value);
      },
      removeAttribute(name) {
        delete this.attrs[name];
      },
      appendChild(child) {
        child.parent = this;
        this.children.push(child);
      },
      remove() {
        if (this.parent) this.parent.children = this.parent.children.filter((c) => c !== this);
        this.parent = null;
      },
      play() {
        this.plays += 1;
        this.paused = false;
        return Promise.resolve();
      },
      pause() {
        this.paused = true;
      },
    };
    Object.defineProperty(el, "ownerDocument", { get: () => doc });
    return el;
  };
  const doc = { createElement: make };
  return doc;
}

test("mountAvatar crossfades between the talking clip and the poster, and cleans up", () => {
  const doc = fakeDocument();
  const container = doc.createElement("div");
  const session = fakeSession();
  const changes = [];
  const avatar = mountAvatar(container, session, {
    talking: "/talking.mp4",
    poster: "/still.jpg",
    speakingHoldMs: 0,
    onStateChange: (s) => changes.push(s),
  });
  const root = container.children[0];
  const [img, video] = root.children;
  assert.equal(img.tagName, "IMG");
  assert.equal(video.tagName, "VIDEO");
  assert.equal(video.muted, true);
  assert.equal(video.loop, true);
  assert.equal(container.attrs["data-relay-avatar-state"], "idle");

  session.emit("SPEECH_STARTED");
  assert.equal(avatar.state, "speaking");
  assert.equal(container.attrs["data-relay-avatar-state"], "speaking");
  assert.equal(video.style.opacity, "1");
  assert.equal(video.plays, 1);

  session.emit("SPEECH_STOPPED");
  assert.equal(avatar.state, "idle");
  assert.equal(video.style.opacity, "0");
  assert.deepEqual(changes, ["idle", "speaking", "idle"]);

  avatar.destroy();
  assert.equal(container.children.length, 0);
  assert.equal(container.attrs["data-relay-avatar-state"], undefined);
  assert.equal(session.count(), 0);
});

test("mountAvatar shares one video between states that use the same clip, and requires a talking clip", () => {
  const doc = fakeDocument();
  const container = doc.createElement("div");
  const avatar = mountAvatar(container, fakeSession(), { talking: "/t.mp4", idle: "/i.mp4", thinking: "/i.mp4" });
  const videos = container.children[0].children.filter((c) => c.tagName === "VIDEO");
  assert.equal(videos.length, 2);
  const idle = videos.find((v) => v.src === "/i.mp4");
  assert.equal(idle.style.opacity, "1"); // idle clip visible from the start
  assert.notEqual(videos.find((v) => v.src === "/t.mp4").style.opacity, "1");
  avatar.destroy();
  assert.throws(() => mountAvatar(container, fakeSession(), {}), /talking/);
});

test("idleInterval shows the poster and plays the idle clip once at random intervals", async () => {
  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  const doc = fakeDocument();
  const container = doc.createElement("div");
  const session = fakeSession();
  const avatar = mountAvatar(container, session, {
    talking: "/t.mp4",
    idle: "/i.mp4",
    poster: "/still.jpg",
    idleInterval: [5, 10],
    speakingHoldMs: 0,
  });
  const videos = container.children[0].children.filter((c) => c.tagName === "VIDEO");
  const idle = videos.find((v) => v.src === "/i.mp4");
  const talking = videos.find((v) => v.src === "/t.mp4");
  assert.equal(idle.loop, false);
  assert.equal(talking.loop, true);
  assert.equal(idle.style.opacity, "0"); // poster first
  assert.equal(idle.plays, 0);

  await sleep(30);
  assert.equal(idle.plays, 1); // played once, from the start
  assert.equal(idle.currentTime, 0);
  assert.equal(idle.style.opacity, "1");
  idle.onended();
  assert.equal(idle.style.opacity, "0"); // back to the poster until the next random play

  session.emit("SPEECH_STARTED");
  assert.equal(talking.style.opacity, "1");
  const playsBefore = idle.plays;
  await sleep(30);
  assert.equal(idle.plays, playsBefore); // no idle plays while speaking

  session.emit("SPEECH_STOPPED");
  assert.equal(talking.style.opacity, "0");
  assert.equal(idle.style.opacity, "0");
  avatar.destroy();
  await sleep(30);
  assert.equal(idle.plays, playsBefore); // destroy cancels the pending play

  assert.throws(
    () => mountAvatar(doc.createElement("div"), fakeSession(), { talking: "/t.mp4", idleInterval: [10, 5] }),
    /idleInterval/,
  );
});
