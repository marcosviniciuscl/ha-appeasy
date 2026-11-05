export const toast = {
  add: () => {},
  remove: () => {},
}

export function notify(severity, summary, detail, life = 4000) {
  toast.add({ severity, summary, detail, life })
}
