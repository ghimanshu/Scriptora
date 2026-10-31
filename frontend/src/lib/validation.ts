export function manuscript(file: File, kind = "manuscript") {
  const proof = kind === "payment_proof";
  const max = proof ? 10 * 1024 * 1024 : 20 * 1024 * 1024;
  const extension = file.name.split(".").pop()?.toLowerCase();
  if (
    !(proof ? ["pdf", "png", "jpg", "jpeg"] : ["pdf", "docx"]).includes(
      extension || "",
    )
  )
    return "Choose a supported file type.";
  if (!file.size || file.size > max)
    return `Choose a nonempty file under ${proof ? 10 : 20} MiB.`;
  return null;
}
