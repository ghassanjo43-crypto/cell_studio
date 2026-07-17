// Stub for @iwer/devui — the browser WebXR *emulator* devtools UI that
// @react-three/xr's emulate path pulls in. We pair xr v6 with React Three Fiber
// v8, whose zustand v3 conflicts with the emulator's zustand v4 `create` import,
// breaking the production build. The emulator is a dev-only convenience (fake a
// headset in the browser); real-headset VR never invokes it. Aliasing it to this
// stub removes the conflicting module from the bundle without affecting VR.
//
// `emulate()` only calls `xrdevice.installDevUI(DevUI)`, so a no-op class suffices.

export class DevUI {}

export default { DevUI };
