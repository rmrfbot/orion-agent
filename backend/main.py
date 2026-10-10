from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

app = FastAPI(title="Orion Local API")

app.add_middleware(
	CORSMiddleware,
	allow_origins=["*"],
	allow_methods=["*"],
	allow_headers=["*"],
)


class ExtensionCheck(BaseModel):
	title: str = Field(default="", max_length=500)
	url: str = Field(default="", max_length=2048)
	element_count: int = Field(ge=0, le=60)


@app.get("/health")
def health():
	return {"ok": True, "service": "orion"}


@app.post("/extension-check")
def extension_check(payload: ExtensionCheck):
	return {
		"ok": True,
		"message": "Extension reached the Orion backend.",
		"page_title": payload.title,
		"element_count": payload.element_count,
	}
