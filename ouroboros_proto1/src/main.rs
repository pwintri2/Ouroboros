#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::process::Command;

use eframe::{egui, NativeOptions};
use egui::{Align2, Color32, FontId, Pos2, Rect, Stroke, Vec2};
use reqwest::blocking::Client;
use serde::Deserialize;
use screenshots::Screen;

fn main() -> eframe::Result<()> {
    let mut options = NativeOptions::default();
    options.viewport = options
        .viewport
        .with_inner_size([1280.0, 820.0])
        .with_title("Ouroboros proto 1");

    eframe::run_native(
        "Ouroboros proto 1",
        options,
        Box::new(|cc| Ok(Box::new(OuroborosApp::new(cc)))),
    )
}

#[derive(Clone, Debug)]
struct GuidedStep {
    x: f32,
    y: f32,
    message: String,
}

#[derive(Default)]
struct ScreenshotData {
    width: usize,
    height: usize,
    rgba: Vec<u8>,
    ocr_text: String,
}

#[derive(Default)]
struct OuroborosApp {
    user_goal: String,
    status: String,
    internet_notes: String,
    last_error: String,
    steps: Vec<GuidedStep>,
    screenshot: ScreenshotData,
    texture: Option<egui::TextureHandle>,
}

#[derive(Deserialize, Default)]
struct DuckResult {
    #[serde(rename = "AbstractText")]
    abstract_text: String,
    #[serde(rename = "Answer")]
    answer: String,
    #[serde(rename = "RelatedTopics")]
    related_topics: Vec<RelatedTopic>,
}

#[derive(Deserialize, Default)]
struct RelatedTopic {
    #[serde(rename = "Text")]
    text: Option<String>,
}

impl OuroborosApp {
    fn new(_cc: &eframe::CreationContext<'_>) -> Self {
        Self {
            status: "Klaar. Beschrijf wat je wilt doen en klik op 'Analyseer hulp'.".to_string(),
            user_goal: "Ik wil een bestand uploaden en op versturen klikken".to_string(),
            ..Default::default()
        }
    }

    fn analyze(&mut self, ctx: &egui::Context) {
        self.last_error.clear();
        self.status = "Scherm vastleggen...".to_string();

        match capture_primary_screen() {
            Ok(capture) => {
                self.screenshot = capture;
                self.upload_texture(ctx);
                self.status = "Internetinformatie ophalen...".to_string();
            }
            Err(err) => {
                self.last_error = err;
                self.status = "Schermcapture mislukt.".to_string();
                return;
            }
        }

        self.internet_notes = fetch_internet_hint(&self.user_goal)
            .unwrap_or_else(|e| format!("Geen internetcontext beschikbaar: {e}"));

        self.steps = generate_steps(
            &self.user_goal,
            self.screenshot.width,
            self.screenshot.height,
            &self.screenshot.ocr_text,
            &self.internet_notes,
        );

        self.status = format!(
            "Analyse gereed. {} instructiestappen gegenereerd.",
            self.steps.len()
        );
    }

    fn upload_texture(&mut self, ctx: &egui::Context) {
        if self.screenshot.rgba.is_empty() {
            self.texture = None;
            return;
        }
        let image = egui::ColorImage::from_rgba_unmultiplied(
            [self.screenshot.width, self.screenshot.height],
            &self.screenshot.rgba,
        );
        self.texture = Some(ctx.load_texture(
            "desktop_capture",
            image,
            egui::TextureOptions::default(),
        ));
    }

    fn quick_goal_buttons(&mut self, ui: &mut egui::Ui) {
        ui.label("Snelle acties:");
        ui.horizontal_wrapped(|ui| {
            if ui.button("Bestand uploaden").clicked() {
                self.user_goal = "Ik wil een bestand uploaden en versturen".to_string();
            }
            if ui.button("WiFi instellingen").clicked() {
                self.user_goal = "Ik wil wifi instellingen openen".to_string();
            }
            if ui.button("Printer toevoegen").clicked() {
                self.user_goal = "Ik wil een printer toevoegen".to_string();
            }
            if ui.button("Browser cache legen").clicked() {
                self.user_goal = "Ik wil browser cache legen".to_string();
            }
            if ui.button("App installeren").clicked() {
                self.user_goal = "Ik wil een app installeren".to_string();
            }
        });
    }

    fn draw_overlay(&self, ui: &mut egui::Ui, image_rect: Rect, original_w: f32, original_h: f32) {
        let painter = ui.painter();

        let scale_x = image_rect.width() / original_w.max(1.0);
        let scale_y = image_rect.height() / original_h.max(1.0);

        for (idx, step) in self.steps.iter().enumerate() {
            let target = Pos2::new(
                image_rect.left() + step.x * scale_x,
                image_rect.top() + step.y * scale_y,
            );
            let bubble_anchor = Pos2::new(
                (target.x + 170.0).min(image_rect.right() - 10.0),
                (target.y - 80.0).max(image_rect.top() + 10.0),
            );

            painter.line_segment(
                [bubble_anchor, target],
                Stroke::new(3.0, Color32::RED),
            );
            draw_arrow_head(painter, bubble_anchor, target, Color32::RED);

            let bubble_size = Vec2::new(280.0, 62.0);
            let bubble_rect = Rect::from_min_size(
                Pos2::new(
                    (bubble_anchor.x - bubble_size.x).max(image_rect.left() + 4.0),
                    bubble_anchor.y.max(image_rect.top() + 4.0),
                ),
                bubble_size,
            );

            painter.rect(
                bubble_rect,
                10.0,
                Color32::from_rgba_unmultiplied(250, 250, 250, 230),
                Stroke::new(1.5, Color32::from_rgb(200, 40, 40)),
                egui::StrokeKind::Outside,
            );

            let label = format!("{}. {}", idx + 1, step.message);
            painter.text(
                bubble_rect.center_top() + Vec2::new(0.0, 10.0),
                Align2::CENTER_TOP,
                label,
                FontId::proportional(15.0),
                Color32::from_rgb(30, 30, 30),
            );

            painter.circle_filled(target, 7.0, Color32::RED);
        }
    }
}

impl eframe::App for OuroborosApp {
    fn update(&mut self, ctx: &egui::Context, _frame: &mut eframe::Frame) {
        egui::TopBottomPanel::top("header").show(ctx, |ui| {
            ui.horizontal(|ui| {
                ui.heading("Ouroboros proto 1");
                ui.label("Visuele PC-hulp met rode pijlen en tekstballonnen");
            });
            ui.separator();
            ui.horizontal(|ui| {
                ui.label("Wat wil je doen?");
                ui.add_sized([500.0, 28.0], egui::TextEdit::singleline(&mut self.user_goal));
                if ui
                    .add_sized([160.0, 34.0], egui::Button::new("Analyseer hulp"))
                    .clicked()
                {
                    self.analyze(ctx);
                }
                if ui
                    .add_sized([120.0, 34.0], egui::Button::new("Reset"))
                    .clicked()
                {
                    self.steps.clear();
                    self.internet_notes.clear();
                    self.last_error.clear();
                    self.status = "Reset voltooid. Kies een doel en analyseer opnieuw.".to_string();
                }
            });
            self.quick_goal_buttons(ui);
            ui.label(format!("Status: {}", self.status));
            if !self.last_error.is_empty() {
                ui.colored_label(Color32::from_rgb(200, 20, 20), &self.last_error);
            }
        });

        egui::SidePanel::right("intel").resizable(true).show(ctx, |ui| {
            ui.heading("Internet context");
            ui.separator();
            if self.internet_notes.is_empty() {
                ui.label("Nog geen internetinformatie opgehaald.");
            } else {
                ui.label(&self.internet_notes);
            }
            ui.separator();
            ui.heading("Schermtekst (OCR)");
            if self.screenshot.ocr_text.is_empty() {
                ui.label("Geen OCR-tekst (Tesseract niet gevonden of geen tekst herkend).");
            } else {
                egui::ScrollArea::vertical().max_height(180.0).show(ui, |ui| {
                    ui.label(&self.screenshot.ocr_text);
                });
            }
            ui.separator();
            ui.heading("Staplijst");
            for (i, step) in self.steps.iter().enumerate() {
                ui.label(format!("{}. ({:.0},{:.0}) {}", i + 1, step.x, step.y, step.message));
            }
        });

        egui::CentralPanel::default().show(ctx, |ui| {
            if let Some(texture) = &self.texture {
                let avail = ui.available_size();
                let img_size = texture.size_vec2();
                let scale = (avail.x / img_size.x).min(avail.y / img_size.y).max(0.1);
                let draw_size = img_size * scale;

                let (rect, _) = ui.allocate_exact_size(draw_size, egui::Sense::hover());
                ui.painter().image(
                    texture.id(),
                    rect,
                    Rect::from_min_max(Pos2::new(0.0, 0.0), Pos2::new(1.0, 1.0)),
                    Color32::WHITE,
                );

                self.draw_overlay(ui, rect, img_size.x, img_size.y);
            } else {
                ui.vertical_centered(|ui| {
                    ui.heading("Nog geen schermcapture");
                    ui.label("Klik op 'Analyseer hulp' om je scherm te scannen en visuele stappen te krijgen.");
                });
            }
        });
    }
}

fn draw_arrow_head(painter: &egui::Painter, from: Pos2, to: Pos2, color: Color32) {
    let dir = to - from;
    let len = dir.length().max(1.0);
    let unit = dir / len;

    let head = 16.0;
    let perp = Vec2::new(-unit.y, unit.x);
    let p1 = to - unit * head + perp * (head * 0.45);
    let p2 = to - unit * head - perp * (head * 0.45);

    painter.line_segment([to, p1], Stroke::new(3.0, color));
    painter.line_segment([to, p2], Stroke::new(3.0, color));
}

fn capture_primary_screen() -> Result<ScreenshotData, String> {
    let screens = Screen::all().map_err(|e| format!("Geen schermen gevonden: {e}"))?;
    let primary = screens.first().ok_or_else(|| "Geen primair scherm beschikbaar".to_string())?;
    let image = primary.capture().map_err(|e| format!("Capture fout: {e}"))?;

    let width = image.width() as usize;
    let height = image.height() as usize;
    let bgra = image.into_raw();
    let mut rgba = Vec::with_capacity(bgra.len());

    for px in bgra.chunks_exact(4) {
        rgba.push(px[2]);
        rgba.push(px[1]);
        rgba.push(px[0]);
        rgba.push(px[3]);
    }

    let ocr_text = run_optional_tesseract_ocr(width as u32, height as u32, &rgba).unwrap_or_default();

    Ok(ScreenshotData {
        width,
        height,
        rgba,
        ocr_text,
    })
}

fn run_optional_tesseract_ocr(width: u32, height: u32, rgba: &[u8]) -> Result<String, String> {
    if Command::new("tesseract").arg("--version").output().is_err() {
        return Err("Tesseract ontbreekt op PATH".to_string());
    }

    let tmp_dir = std::env::temp_dir();
    let img_path = tmp_dir.join("ouroboros_proto1_capture.png");
    let out_base = tmp_dir.join("ouroboros_proto1_ocr");

    image::save_buffer(&img_path, rgba, width, height, image::ColorType::Rgba8)
        .map_err(|e| format!("PNG schrijven mislukt: {e}"))?;

    let output = Command::new("tesseract")
        .arg(&img_path)
        .arg(&out_base)
        .arg("-l")
        .arg("eng+nld")
        .output()
        .map_err(|e| format!("Tesseract startfout: {e}"))?;

    if !output.status.success() {
        return Err(String::from_utf8_lossy(&output.stderr).to_string());
    }

    let txt_path = out_base.with_extension("txt");
    std::fs::read_to_string(txt_path).map_err(|e| format!("OCR output lezen mislukt: {e}"))
}

fn fetch_internet_hint(goal: &str) -> Result<String, String> {
    let encoded = urlencoding::encode(goal);
    let url = format!(
        "https://api.duckduckgo.com/?q={encoded}&format=json&no_html=1&skip_disambig=1"
    );

    let client = Client::builder()
        .user_agent("OuroborosProto1/0.1")
        .build()
        .map_err(|e| format!("HTTP client fout: {e}"))?;

    let parsed: DuckResult = client
        .get(url)
        .send()
        .map_err(|e| format!("Netwerkfout: {e}"))?
        .json()
        .map_err(|e| format!("JSON parse fout: {e}"))?;

    let mut notes = Vec::new();

    if !parsed.answer.trim().is_empty() {
        notes.push(format!("Antwoord: {}", parsed.answer));
    }
    if !parsed.abstract_text.trim().is_empty() {
        notes.push(format!("Samenvatting: {}", parsed.abstract_text));
    }

    for t in parsed.related_topics.into_iter().take(3) {
        if let Some(text) = t.text {
            if !text.trim().is_empty() {
                notes.push(format!("Tip: {}", text));
            }
        }
    }

    if notes.is_empty() {
        notes.push("Geen direct resultaat gevonden, gebruik algemene UI-hints.".to_string());
    }

    Ok(notes.join("\n"))
}

fn generate_steps(goal: &str, width: usize, height: usize, ocr_text: &str, internet_hint: &str) -> Vec<GuidedStep> {
    let goal_lc = goal.to_lowercase();
    let ocr_lc = ocr_text.to_lowercase();

    let mut steps = vec![GuidedStep {
        x: width as f32 * 0.42,
        y: height as f32 * 0.14,
        message: "Klik eerst op het venster dat je wilt bedienen".to_string(),
    }];

    if goal_lc.contains("browser") || goal_lc.contains("internet") {
        steps.push(GuidedStep {
            x: width as f32 * 0.2,
            y: height as f32 * 0.06,
            message: "Ga naar de adresbalk en typ de gewenste website".to_string(),
        });
    }

    if goal_lc.contains("upload") || ocr_lc.contains("upload") || ocr_lc.contains("bestand") {
        steps.push(GuidedStep {
            x: width as f32 * 0.28,
            y: height as f32 * 0.58,
            message: "Klik op 'Upload' of 'Bestand kiezen'".to_string(),
        });
        steps.push(GuidedStep {
            x: width as f32 * 0.55,
            y: height as f32 * 0.72,
            message: "Selecteer je bestand en bevestig met Openen".to_string(),
        });
    }

    if goal_lc.contains("verstuur") || goal_lc.contains("send") || ocr_lc.contains("send") {
        steps.push(GuidedStep {
            x: width as f32 * 0.78,
            y: height as f32 * 0.87,
            message: "Klik op de knop Versturen/Send".to_string(),
        });
    }

    if goal_lc.contains("instelling") || goal_lc.contains("settings") {
        steps.push(GuidedStep {
            x: width as f32 * 0.95,
            y: height as f32 * 0.06,
            message: "Open instellingen via tandwiel of menu rechtsboven".to_string(),
        });
    }

    if steps.len() == 1 {
        steps.push(GuidedStep {
            x: width as f32 * 0.5,
            y: height as f32 * 0.5,
            message: "Zoek de hoofdactieknop die past bij je doel".to_string(),
        });
    }

    steps.push(GuidedStep {
        x: width as f32 * 0.7,
        y: height as f32 * 0.12,
        message: compact_hint(internet_hint),
    });

    steps
}

fn compact_hint(hint: &str) -> String {
    let first = hint.lines().next().unwrap_or("Gebruik de volgende logische stap");
    let clipped: String = first.chars().take(72).collect();
    format!("Web tip: {clipped}")
}
