"""전체 파이프라인 실행: h5ad 메타데이터 추출 -> HTML 리포트 생성."""

import extract_metadata
import generate_report


def main():
    extract_metadata.main()
    generate_report.main()


if __name__ == "__main__":
    main()
