import Foundation
import Vision
import CoreGraphics
import ImageIO

func recognize(_ path: String) throws -> String {
    let url = URL(fileURLWithPath: path)
    guard let source = CGImageSourceCreateWithURL(url as CFURL, nil),
          let image = CGImageSourceCreateImageAtIndex(source, 0, nil) else {
        throw NSError(domain: "VisionOCR", code: 1, userInfo: [NSLocalizedDescriptionKey: "无法读取图片"])
    }

    var recognized: [String] = []
    let request = VNRecognizeTextRequest { request, error in
        if error != nil { return }
        let observations = request.results as? [VNRecognizedTextObservation] ?? []
        recognized = observations.compactMap { observation in
            observation.topCandidates(1).first?.string
        }
    }
    request.recognitionLevel = .accurate
    request.usesLanguageCorrection = true
    request.recognitionLanguages = ["zh-Hans", "zh-Hant", "en-US"]

    let handler = VNImageRequestHandler(cgImage: image, options: [:])
    try handler.perform([request])
    return recognized.joined(separator: "\n")
}

let paths = Array(CommandLine.arguments.dropFirst())
if paths.isEmpty {
    fputs("usage: vision_ocr <image-path> [image-path...]\n", stderr)
    exit(2)
}

var exitCode: Int32 = 0
for path in paths {
    do {
        print("###FILE:\(path)")
        print(try recognize(path))
    } catch {
        exitCode = 1
        fputs("OCR failed for \(path): \(error.localizedDescription)\n", stderr)
    }
}
exit(exitCode)
