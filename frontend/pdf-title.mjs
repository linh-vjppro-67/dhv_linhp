export async function requestPdfTitle(url, options) {
  for (let attempt = 0; attempt < 2; attempt++) {
    const response = await fetch(url, options);
    const text = await response.text();
    let result;
    try {
      result = JSON.parse(text);
    } catch {
      if (attempt === 0 && (response.ok || [502, 503, 504].includes(response.status))) continue;
      throw Error("Máy chủ nhận diện chưa trả về dữ liệu hợp lệ. Vui lòng chọn lại tệp để thử lại");
    }
    if (!response.ok) {
      throw Error(typeof result?.detail === "string" ? result.detail : `Không thể nhận diện tên văn bản (${response.status})`);
    }
    if (typeof result?.title !== "string" || !result.title.trim()) {
      throw Error("AI chưa nhận diện được tiêu đề trong văn bản");
    }
    return { ...result, title: result.title.trim() };
  }
}
