export type Tick = number

declare module 'claude-code' {
  interface PluginState {
    'gopher-spinner': { tick: Tick }
  }
}
