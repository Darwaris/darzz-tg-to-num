export default async function handler(req, res) {
  const tgid = req.query.id;

  if (!tgid) {
    return res.status(400).json({
      success: false,
      error: "Missing telegram id"
    });
  }

  try {
    const r = await fetch(
      "https://tg-to-num-vishal.vercel.app/api/search?number=" + tgid
    );

    const data = await r.json();
    return res.status(200).json(data);

  } catch (e) {
    return res.status(500).json({
      success: false,
      error: "Proxy failed"
    });
  }
}
