import { call, download } from "../../repair-api.js";
import { time } from "../../app/format.js";
import { useEffect, useState } from "react";

export function Photo({ file }) {
  const [url, setUrl] = useState("");
  useEffect(() => {
    let alive = true,
      object;
    call("/v2/files/" + file.id + "?thumb=true", { raw: true })
      .then((blob) => {
        object = URL.createObjectURL(blob);
        if (alive) setUrl(object);
        else URL.revokeObjectURL(object);
      })
      .catch(() => {});
    return () => {
      alive = false;
      if (object) URL.revokeObjectURL(object);
    };
  }, [file.id]);
  return (
    <figure>
      <button onClick={() => download("/v2/files/" + file.id, file.filename)}>
        {url ? <img src={url} alt={file.filename} /> : <span>Фото</span>}
      </button>
      <figcaption>
        {file.phase} · {time(file.created_at)}
      </figcaption>
    </figure>
  );
}
