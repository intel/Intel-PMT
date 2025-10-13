// Copyright 2025 Intel Corporation
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

package intelpmtreceiver

import (
	"encoding/xml"
	"errors"
	"html"
	"io"
	"math"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"time"

	"go.uber.org/zap"
)

type DateOnly struct {
	time.Time
}

func (do *DateOnly) UnmarshalXML(d *xml.Decoder, start xml.StartElement) error {
	var dateString string
	err := d.DecodeElement(&dateString, &start)
	if err != nil {
		return err
	}
	parsedDate, err := time.Parse(time.DateOnly, dateString)
	if err != nil {
		return err
	}
	*do = DateOnly{parsedDate}
	return nil
}

type PMTMetadata struct {
	XMLName     xml.Name    `xml:"pmt"`
	LastUpdated DateOnly    `xml:"lastupdated"`
	Mappings    PMTMappings `xml:"mappings"`
	BasePath    string      `xml:"-"`
}
type PMTMappings struct {
	XMLName xml.Name     `xml:"mappings"`
	Mapping []PMTMapping `xml:"mapping"`
}

type PMTMapping struct {
	XMLName     xml.Name `xml:"mapping"`
	GUID        string   `xml:"guid,attr"`
	Size        string   `xml:"size,attr"`
	LastUpdated DateOnly `xml:"lastupdated"`
	Status      string   `xml:"status"`
	Description string   `xml:"description"`
	XMLSet      XMLSet   `xml:"xmlset"`
}

type XMLSet struct {
	XMLName             xml.Name `xml:"xmlset"`
	Basedir             string   `xml:"basedir"`
	Common              string   `xml:"common"`
	Aggregator          string   `xml:"aggregator"`
	AggregatorInterface string   `xml:"aggregatorinterface"`
}

type PMTAggKey struct {
	GUID string
	Size uint64
}

type PMTLookupMap map[PMTAggKey]XMLSet

type Unit struct {
	XMLName xml.Name `xml:"units"`
	Name    string   `xml:"name,attr"`
	Symbol  string   `xml:"symbol"`
}

type Enum struct {
	XMLName     xml.Name `xml:"enum_item"`
	Name        string   `xml:"name"`
	Encoding    string   `xml:"encoding"`
	Value       string   `xml:"value"`
	DataType    string   `xml:"dataType"`
	Description string   `xml:"description"`
}
type DataType struct {
	XMLName    xml.Name `xml:"dataType"`
	Name       string   `xml:"name,attr"`
	DataTypeID string   `xml:"datatypeID,attr"`
	DataClass  string   `xml:"dataclass"`
	Unit       Unit     `xml:"units,omitempty"`
	Enums      []Enum   `xml:"enum>enum_item,omitempty"`
}

type DataTypes struct {
	XMLName   xml.Name   `xml:"DataTypes"`
	DataTypes []DataType `xml:"dataType"`
}

type Aggregator struct {
	XMLName     xml.Name      `xml:"Aggregator"`
	Name        string        `xml:"name"`
	Description string        `xml:"description"`
	GUID        string        `xml:"uniqueid"`
	SampleGroup []SampleGroup `xml:"SampleGroup"`
}

type SampleGroup struct {
	XMLName  xml.Name `xml:"SampleGroup"`
	SampleID uint64   `xml:"sampleID,attr"`
	Sample   []Sample `xml:"sample"`
}

type Sample struct {
	XMLName       xml.Name `xml:"sample"`
	SampleName    string   `xml:"name,attr"`
	DatatypeIDRef string   `xml:"datatypeIDREF,attr"`
	SampleID      string   `xml:"sampleID,attr"`
	SubGroup      string   `xml:"sampleSubGroup"`
	SampleType    string   `xml:"sampleType"`
	Lsb           uint64   `xml:"lsb"`
	Msb           uint64   `xml:"msb"`

	// calculated value for convenience
	CalculatedByteOffset uint64 `xml:"-"`
	CalculatedMask       uint64 `xml:"-"`
}

type AggregatorInterface struct {
	XMLName           xml.Name          `xml:"AggregatorInterface"`
	Transformations   Transformations   `xml:"TransFormations"`
	AggregatorSamples AggregatorSamples `xml:"AggregatorSamples"`
}

type Transformations struct {
	XMLName        xml.Name         `xml:"TransFormations"`
	Transformation []Transformation `xml:"TransFormation"`
}

type Transformation struct {
	XMLName     xml.Name `xml:"TransFormation"`
	Name        string   `xml:"name,attr"`
	TransformID string   `xml:"transformID,attr"`
	Transform   string   `xml:"transform"`
}

type AggregatorSamples struct {
	XMLName          xml.Name           `xml:"AggregatorSamples"`
	AggregatorSample []AggregatorSample `xml:"T_AggregatorSample"`
}

type AggregatorSample struct {
	XMLName         xml.Name        `xml:"T_AggregatorSample"`
	SampleName      string          `xml:"sampleName,attr"`
	SampleType      string          `xml:"SampleType"`
	SampleGroup     string          `xml:"sampleGroup,attr"`
	DatatypeIDRef   string          `xml:"datatypeIDREF,attr"`
	Description     string          `xml:"description"`
	TransformInputs TransformInputs `xml:"TransFormInputs"`
	TransformREF    string          `xml:"transformREF"`

	// populated after unmarshalling
	TransformFormula string `xml:"-"`
}

type TransformInputs struct {
	XMLName        xml.Name         `xml:"TransFormInputs"`
	TransformInput []TransformInput `xml:"TransFormInput"`
}

type TransformInput struct {
	XMLName     xml.Name `xml:"TransFormInput"`
	VarName     string   `xml:"varName,attr"`
	SampleIDREF string   `xml:"sampleIDREF"`
}

func GetPMTMetadata(filePath string, meta *PMTMetadata) error {
	fpmtmeta, err := os.Open(filePath)
	if err != nil {
		return err
	}
	defer fpmtmeta.Close()
	byteValue, err := io.ReadAll(fpmtmeta)
	if err != nil {
		return err
	}

	err = xml.Unmarshal(byteValue, &meta)
	if err != nil {
		return err
	}

	for guid, mapping := range meta.Mappings.Mapping {
		mapping.GUID = strings.ToUpper(mapping.GUID)
		meta.Mappings.Mapping[guid] = mapping
	}
	absPath, err := filepath.Abs(filePath)
	if err != nil {
		return err
	}
	meta.BasePath = filepath.Dir(absPath)
	return nil
}

func GetPMTCommonDatatypes(filePath string, common *DataTypes) error {
	file, err := os.Open(filePath)
	if err != nil {
		return err
	}
	defer file.Close()
	byteValue, err := io.ReadAll(file)
	if err != nil {
		return err
	}

	err = xml.Unmarshal(byteValue, &common)
	if err != nil {
		return err
	}
	return nil
}

func CalculateMask(msb uint64, lsb uint64) uint64 {
	msbMask := math.MaxUint64 & ((uint64(1) << (msb + 1)) - 1)
	lsbMask := math.MaxUint64 & ((uint64(1) << lsb) - 1)
	return msbMask & (^lsbMask)
}

func GetPMTAggregator(filePath string, agg *Aggregator) error {
	file, err := os.Open(filePath)
	if err != nil {
		return err
	}
	defer file.Close()
	byteValue, err := io.ReadAll(file)
	if err != nil {
		return err
	}
	// WA: go xml parser does not understand XML entity reference
	stringRep := strings.ReplaceAll(string(byteValue), "&otherfile;", "")
	err = xml.Unmarshal([]byte(stringRep), &agg)
	if err != nil {
		return err
	}
	// calculate mask for every sample definition
	for groupIdx, group := range agg.SampleGroup {
		sampleID := group.SampleID
		for sampleIdx, sample := range group.Sample {
			msb := sample.Msb
			lsb := sample.Lsb
			agg.SampleGroup[groupIdx].Sample[sampleIdx].CalculatedByteOffset = sampleID * sampleSizeBytes // byte offset from the beginning aggregator space
			agg.SampleGroup[groupIdx].Sample[sampleIdx].CalculatedMask = CalculateMask(msb, lsb)
		}
	}
	return nil
}

func transformEquation(equation string) string {
	withoutDollar := strings.ReplaceAll(equation, "$", "")
	decoded := html.UnescapeString(withoutDollar)
	return decoded
}

func GetPMTAggregatorInterface(filePath string, agi *AggregatorInterface) error {
	file, err := os.Open(filePath)
	if err != nil {
		return err
	}
	defer file.Close()
	byteValue, err := io.ReadAll(file)
	if err != nil {
		return err
	}
	err = xml.Unmarshal(byteValue, &agi)
	if err != nil {
		return err
	}
	var transformationMap = make(map[string]string)
	for _, transformation := range agi.Transformations.Transformation {
		transformationMap[transformation.TransformID] = transformEquation(transformation.Transform)
	}
	for sampleIndex, aggregatorSample := range agi.AggregatorSamples.AggregatorSample {
		transformRef := aggregatorSample.TransformREF
		if formula, ok := transformationMap[transformRef]; ok {
			agi.AggregatorSamples.AggregatorSample[sampleIndex].TransformFormula = formula
		}
	}
	return nil
}

func BuildLookupMap(meta PMTMetadata, logger *zap.Logger) (PMTLookupMap, error) {
	if len(meta.Mappings.Mapping) == 0 {
		return nil, errors.New("no mappings found")
	}

	lookupMap := make(PMTLookupMap)
	for _, mapping := range meta.Mappings.Mapping {
		// Normalize GUID: convert to lowercase and remove 0x prefix if present
		normalizedGUID := strings.ToLower(strings.TrimSpace(mapping.GUID))

		// Validate that the normalized GUID is a valid hexadecimal string
		_, err := strconv.ParseInt(normalizedGUID[2:], 16, 64)
		if err != nil || !strings.HasPrefix(normalizedGUID, "0x") {
			logger.Warn("Invalid GUID format in metadata XML",
				zap.String("guid", mapping.GUID))
			continue
		}

		size, err := strconv.ParseUint(mapping.Size, 10, 64)
		if err != nil {
			logger.Warn("Invalid size format in metadata XML",
				zap.String("guid", mapping.GUID),
				zap.String("size", mapping.Size))
			continue
		}

		// check if key is in the map
		if _, isPresent := lookupMap[PMTAggKey{normalizedGUID, size}]; isPresent {
			logger.Warn("Aggregator already exists in lookup map",
				zap.String("guid", normalizedGUID),
				zap.Uint64("size", size))
			continue
		}

		xmlSet := mapping.XMLSet
		basePath := strings.Join(strings.Split(xmlSet.Basedir, "/"), string(os.PathSeparator))
		xmlSet.Basedir = meta.BasePath + string(os.PathSeparator) + basePath

		lookupMap[PMTAggKey{normalizedGUID, size}] = xmlSet
	}

	return lookupMap, nil
}

func FindXMLSetForGUIDSize(lookupMap PMTLookupMap, guid string, size uint64) (XMLSet, error) {
	if lookupMap == nil {
		return XMLSet{}, errors.New("nil lookup map")
	}

	xmlSet, ok := lookupMap[PMTAggKey{guid, size}]
	if ok {
		return xmlSet, nil
	}
	return XMLSet{}, errors.New(
		"Aggregator not found in lookup map: " + guid + ", size: " + strconv.FormatUint(size, 10),
	)
}
