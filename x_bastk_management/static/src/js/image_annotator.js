/** @odoo-module **/

import { Component, useState, useRef, onMounted } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

export class ImageAnnotatorField extends Component {
    static template = "x_bastk_management.ImageAnnotatorField";
    static props = {
        ...standardFieldProps,
    };
    
    setup() {
        this.canvasRef = useRef("drawCanvas");
        this.state = useState({
            color: "#ff0000",
            lineWidth: 3,
            isDrawing: false,
            imgLoaded: false,
        });
        
        this.context = null;
        this.img = new Image();
        
        onMounted(() => {
            if (this.canvasRef.el) {
                this.context = this.canvasRef.el.getContext("2d");
                this._loadImage();
            }
        });
    }

    _getImageUrl(fieldName) {
        const val = this.props.record.data[fieldName];
        if (!val) return "";
        if (typeof val === 'string' && val.length > 100) {
            return val.startsWith('data:image') ? val : "data:image/png;base64," + val;
        }
        if (this.props.record.resId) {
            const unique = this.props.record.data.write_date ? String(this.props.record.data.write_date) : "";
            return `/web/image?model=${this.props.record.resModel}&id=${this.props.record.resId}&field=${fieldName}&unique=${unique}`;
        }
        return "";
    }

    _loadImage() {
        let url = this._getImageUrl(this.props.name);
        
        if (!url) {
            // fallback to original image field
            url = this._getImageUrl('image');
        }

        if (url) {
            this.img.onload = () => {
                const canvas = this.canvasRef.el;
                canvas.width = this.img.width;
                canvas.height = this.img.height;
                this.context.drawImage(this.img, 0, 0);
                this.state.imgLoaded = true;
            };
            this.img.crossOrigin = "Anonymous";
            this.img.src = url;
        } else {
            // empty canvas
            const canvas = this.canvasRef.el;
            canvas.width = 800;
            canvas.height = 600;
            this.context.fillStyle = "#ffffff";
            this.context.fillRect(0, 0, canvas.width, canvas.height);
        }
    }

    _getCoordinates(e) {
        const canvas = this.canvasRef.el;
        const rect = canvas.getBoundingClientRect();
        const scaleX = canvas.width / rect.width;
        const scaleY = canvas.height / rect.height;
        
        let clientX = e.clientX;
        let clientY = e.clientY;
        
        if (e.touches && e.touches.length > 0) {
            clientX = e.touches[0].clientX;
            clientY = e.touches[0].clientY;
        }
        
        return {
            x: (clientX - rect.left) * scaleX,
            y: (clientY - rect.top) * scaleY
        };
    }

    _onMouseDown(e) {
        if (this.props.readonly) return;
        this.state.isDrawing = true;
        const pos = this._getCoordinates(e);
        this.context.beginPath();
        this.context.moveTo(pos.x, pos.y);
    }

    _onMouseMove(e) {
        if (!this.state.isDrawing || this.props.readonly) return;
        const pos = this._getCoordinates(e);
        this.context.lineTo(pos.x, pos.y);
        this.context.strokeStyle = this.state.color;
        this.context.lineWidth = this.state.lineWidth;
        this.context.lineCap = "round";
        this.context.lineJoin = "round";
        this.context.stroke();
    }

    _onMouseUp(e) {
        if (!this.state.isDrawing || this.props.readonly) return;
        this.state.isDrawing = false;
        this.context.closePath();
        
        // Update the record with the new image data
        const canvas = this.canvasRef.el;
        const dataUrl = canvas.toDataURL("image/png");
        const base64Data = dataUrl.split(",")[1];
        this.props.record.update({ [this.props.name]: base64Data });
    }

    _onTouchStart(e) {
        // Only prevent default on touch to stop scrolling if not readonly
        if (!this.props.readonly) {
            e.preventDefault();
        }
        this._onMouseDown(e);
    }

    _onTouchMove(e) {
        if (!this.props.readonly) {
            e.preventDefault();
        }
        this._onMouseMove(e);
    }

    _onTouchEnd(e) {
        if (!this.props.readonly) {
            e.preventDefault();
        }
        this._onMouseUp(e);
    }

    _onClear() {
        this.context.clearRect(0, 0, this.canvasRef.el.width, this.canvasRef.el.height);
        // Reload original image (not annotated)
        const url = this._getImageUrl('image');
        if (url) {
            const originalImg = new Image();
            originalImg.onload = () => {
                const canvas = this.canvasRef.el;
                canvas.width = originalImg.width;
                canvas.height = originalImg.height;
                this.context.drawImage(originalImg, 0, 0);
                
                // Clear the annotation in the record
                const dataUrl = canvas.toDataURL("image/png");
                const base64Data = dataUrl.split(",")[1];
                this.props.record.update({ [this.props.name]: base64Data });
            };
            originalImg.crossOrigin = "Anonymous";
            originalImg.src = url;
        } else {
             this.context.fillStyle = "#ffffff";
             this.context.fillRect(0, 0, this.canvasRef.el.width, this.canvasRef.el.height);
             const dataUrl = this.canvasRef.el.toDataURL("image/png");
             const base64Data = dataUrl.split(",")[1];
             this.props.record.update({ [this.props.name]: base64Data });
        }
    }
}

export const imageAnnotatorField = {
    component: ImageAnnotatorField,
    supportedTypes: ["binary"],
};

registry.category("fields").add("image_annotator", imageAnnotatorField);
