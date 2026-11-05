export async function api(path, body) {
  const options = body === undefined
    ? {}
    : {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Requested-With': 'HA-Concierge',
        },
        body: JSON.stringify(body),
      }

  const response = await fetch(`./api/${path}`, options)
  let data = {}
  try {
    data = await response.json()
  } catch {
    data = {}
  }
  if (!response.ok) {
    throw new Error(data.error || `Erro ${response.status}`)
  }
  return data
}
