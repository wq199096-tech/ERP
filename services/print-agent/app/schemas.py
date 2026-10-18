from typing import Literal

from pydantic import BaseModel, Field, model_validator


class LabelElement(BaseModel):
    kind: Literal["text", "sku", "barcode", "qrcode", "price"]
    x_mm: float = Field(ge=0)
    y_mm: float = Field(ge=0)
    width_mm: float = Field(gt=0)
    height_mm: float = Field(gt=0)
    value: str = Field(default="", max_length=500)


class LabelTemplate(BaseModel):
    schema_version: Literal[1] = 1
    name: str = Field(default="商品标签", min_length=1, max_length=100)
    width_mm: float = Field(ge=20, le=210)
    height_mm: float = Field(ge=15, le=297)
    elements: list[LabelElement] = Field(min_length=1, max_length=50)

    @model_validator(mode="after")
    def elements_inside_page(self) -> "LabelTemplate":
        for element in self.elements:
            if (
                element.x_mm + element.width_mm > self.width_mm
                or element.y_mm + element.height_mm > self.height_mm
            ):
                raise ValueError(f"{element.kind} 元素超出标签边界")
        return self
